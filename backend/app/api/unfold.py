"""API routes for sheet-metal unfolding."""
from __future__ import annotations
import tempfile
import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import json

from build123d import import_step, Solid, Compound
from app.services.unfold_service import unfold, UnfoldRequest
from app.models.unfold import (
    Unfolded, BendRecord, UnfoldResponse, UnfoldErrorCode, BendDirection
)
from app.core.config import get_settings


router = APIRouter(prefix="/api/unfold", tags=["unfold"])


class UnfoldParams(BaseModel):
    k_factor: float = Field(default=0.33, ge=0.0, le=1.0)
    kerf: float = Field(default=0.0, ge=0.0)
    bend_table: Optional[str] = None  # JSON string


class BendRecordOut(BaseModel):
    index: int
    angle_deg: float
    direction: str
    inside_radius: float
    bend_allowance: float
    k_factor: float
    bend_line_start: List[float]
    bend_line_end: List[float]
    flange_length_side_a: float
    flange_length_side_b: float
    nearest_cut_distance: float
    axis_point: List[float]
    axis_direction: List[float]


class UnfoldedOut(BaseModel):
    profile_svg: str  # SVG representation of flat pattern
    bend_lines: List[List[List[float]]]
    bends: List[BendRecordOut]
    thickness: float
    k_factor: float
    kerf: float
    blank_area: float
    volume: float
    material_conservation_ratio: float
    warnings: List[str]


class UnfoldResponseOut(BaseModel):
    success: bool
    unfolded: Optional[UnfoldedOut] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: float


def _profile_to_svg(profile, scale: float = 1.0) -> str:
    """Convert build123d profile to SVG for frontend visualization."""
    from build123d import bounding_box, Compound, Face, Edge, Wire
    from build123d import edges, faces, vertices

    if profile is None:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>'

    # Get bounds
    bb = bounding_box(profile)
    min_x, min_y = bb.min.X, bb.min.Y
    max_x, max_y = bb.max.X, bb.max.Y
    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>'

    # Add padding
    padding = max(width, height) * 0.05
    viewbox_min_x = min_x - padding
    viewbox_min_y = min_y - padding
    viewbox_width = width + 2 * padding
    viewbox_height = height + 2 * padding

    # Collect paths
    paths = []
    for face in faces(profile):
        for wire in face.wires():
            path_commands = []
            for edge in wire.edges():
                curve = edge.geom_type
                # Simplified: approximate with line segments
                # In production, use proper curve-to-SVG conversion
                verts = list(vertices(edge))
                if len(verts) >= 2:
                    pts = [(v.X, v.Y) for v in verts]
                    if path_commands:
                        path_commands.append(f"M {pts[0][0]:.3f} {pts[0][1]:.3f}")
                    else:
                        path_commands.append(f"M {pts[0][0]:.3f} {pts[0][1]:.3f}")
                    for pt in pts[1:]:
                        path_commands.append(f"L {pt[0]:.3f} {pt[1]:.3f}")
            if path_commands:
                paths.append(" ".join(path_commands) + " Z")

    svg_content = " ".join(paths) if paths else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox_min_x:.3f} {viewbox_min_y:.3f} {viewbox_width:.3f} {viewbox_height:.3f}">
  <g fill="none" stroke="#2563eb" stroke-width="{max(width, height) * 0.003:.3f}">
    <path d="{svg_content}"/>
  </g>
</svg>'''


def _bend_lines_to_svg(bend_lines, profile, scale: float = 1.0) -> str:
    """Generate SVG for bend lines."""
    if not bend_lines:
        return ""

    lines = []
    for (x1, y1), (x2, y2) in bend_lines:
        lines.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="#dc2626" stroke-width="{max(1, (bounding_box(profile).max.X - bounding_box(profile).min.X) * 0.002):.3f}" stroke-dasharray="5,5"/>')
    return "\n".join(lines)


@router.post("", response_model=UnfoldResponseOut)
async def unfold_step_file(
    file: UploadFile = File(..., description="STEP file (.step, .stp)"),
    k_factor: float = Form(default=0.33),
    kerf: float = Form(default=0.0),
    bend_table: Optional[str] = Form(default=None)
):
    """Unfold a sheet-metal part from a STEP file."""
    settings = get_settings()

    # Validate file
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".step", ".stp"]:
        raise HTTPException(400, "File must be a STEP file (.step or .stp)")

    # Check file size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large (max {settings.MAX_UPLOAD_SIZE} bytes)")

    # Save to temp file for import_step
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Import STEP
        shape = import_step(tmp_path)
        if not isinstance(shape, Solid):
            # Try to extract solid from compound
            if isinstance(shape, Compound):
                solids = [s for s in shape.solids()]
                if len(solids) == 1:
                    shape = solids[0]
                else:
                    raise HTTPException(400, f"STEP contains {len(solids)} solids, expected 1")
            else:
                raise HTTPException(400, "STEP file does not contain a valid solid")

        # Run unfold
        bt = json.loads(bend_table) if bend_table else None
        request = UnfoldRequest(k_factor=k_factor, kerf=kerf, bend_table=bt)
        from app.services.unfold_service import UnfoldService
        service = UnfoldService(request)
        result = service.unfold(shape)

        if not result.success:
            return UnfoldResponseOut(
                success=False,
                error_code=result.error_code.value if result.error_code else "UNKNOWN",
                error_message=result.error_message,
                processing_time_ms=result.processing_time_ms
            )

        # Generate SVG for profile
        profile_svg = _profile_to_svg(result.unfolded.profile)
        # Add bend lines to SVG
        bend_svg = _bend_lines_to_svg(result.unfolded.bend_lines, result.unfolded.profile)
        if bend_svg:
            # Inject bend lines into SVG
            profile_svg = profile_svg.replace("</g>", f"{bend_svg}\n  </g>")

        # Convert bend records
        bends_out = [
            BendRecordOut(
                index=b.index,
                angle_deg=b.angle_deg,
                direction=b.direction.value,
                inside_radius=b.inside_radius,
                bend_allowance=b.bend_allowance,
                k_factor=b.k_factor,
                bend_line_start=list(b.bend_line_start),
                bend_line_end=list(b.bend_line_end),
                flange_length_side_a=b.flange_length_side_a,
                flange_length_side_b=b.flange_length_side_b,
                nearest_cut_distance=b.nearest_cut_distance,
                axis_point=list(b.axis_point),
                axis_direction=list(b.axis_direction)
            )
            for b in result.unfolded.bends
        ]

        unfolded_out = UnfoldedOut(
            profile_svg=profile_svg,
            bend_lines=[[list(s), list(e)] for s, e in result.unfolded.bend_lines],
            bends=bends_out,
            thickness=result.unfolded.thickness,
            k_factor=result.unfolded.k_factor,
            kerf=result.unfolded.kerf,
            blank_area=result.unfolded.blank_area,
            volume=result.unfolded.volume,
            material_conservation_ratio=result.unfolded.material_conservation_ratio,
            warnings=result.unfolded.warnings
        )

        return UnfoldResponseOut(
            success=True,
            unfolded=unfolded_out,
            processing_time_ms=result.processing_time_ms
        )

    finally:
        # Cleanup
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "unfold"}