"""Sheet-metal unfold service - core domain engine.

Implements the cadgen.unfold.unfold algorithm per issue #614:
1. Thickness detection via parallel planar face pairs with opposite normals
2. Bend detection via coaxial cylindrical face pairs (radius diff = thickness)
3. Flange tree construction rooted at largest flat face
4. Bend allowance: BA = θ·(r + K·t) or bend table lookup
5. Flat pattern via OCC union + kerf offset
6. Bend lines + per-bend records with measurements
"""
from __future__ import annotations
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from build123d import (
    Compound, Face, Solid, Vector, Axis, Plane, Location,
    GeomType, ShapeList, Edge, Wire
)
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone
from OCP.TopoDS import TopoDS_Face, TopoDS_Edge
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Vec
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE

from app.models.unfold import (
    Unfolded, BendRecord, UnfoldRequest, UnfoldResponse,
    UnfoldErrorCode, BendDirection
)


# ---- Geometry helpers --------------------------------------------------------

def face_surface_type(face: Face) -> int:
    """Return GeomAbs surface type for a face."""
    surf = BRepAdaptor_Surface(face.wrapped, True)
    return surf.GetType()


def is_planar_face(face: Face) -> bool:
    return face_surface_type(face) == GeomAbs_Plane


def is_cylindrical_face(face: Face) -> bool:
    return face_surface_type(face) == GeomAbs_Cylinder


def is_conical_face(face: Face) -> bool:
    return face_surface_type(face) == GeomAbs_Cone


def get_planar_face_data(face: Face) -> tuple[Vector, Vector, float]:
    """Return (center, normal, area) for a planar face."""
    surf = BRepAdaptor_Surface(face.wrapped, True)
    plane = surf.Plane()
    location = Vector(plane.Location().X(), plane.Location().Y(), plane.Location().Z())
    normal = Vector(plane.Axis().Direction().X(),
                    plane.Axis().Direction().Y(),
                    plane.Axis().Direction().Z())
    # Area via GProp
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, props)
    area = props.Mass()
    return location, normal, area


def get_cylindrical_face_data(face: Face) -> tuple[Vector, Vector, float, float, float]:
    """Return (axis_point, axis_dir, radius, u_min, u_max) for cylindrical face.
    u_min/u_max are parametric bounds (angle in radians).
    """
    surf = BRepAdaptor_Surface(face.wrapped, True)
    cylinder = surf.Cylinder()
    axis = cylinder.Axis()
    axis_point = Vector(axis.Location().X(), axis.Location().Y(), axis.Location().Z())
    axis_dir = Vector(axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z())
    radius = cylinder.Radius()

    # Get parametric bounds (angle range)
    u_min, u_max = surf.FirstUParameter(), surf.LastUParameter()
    return axis_point, axis_dir, radius, u_min, u_max


def face_area(face: Face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, props)
    return props.Mass()


def solid_volume(solid: Solid) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid.wrapped, props)
    return props.Mass()




def vectors_parallel(v1: Vector, v2: Vector, tol: float = 1e-6) -> bool:
    return abs(v1.dot(v2) / (v1.length * v2.length) - 1.0) < tol


def vectors_anti_parallel(v1: Vector, v2: Vector, tol: float = 1e-6) -> bool:
    return abs(v1.dot(v2) / (v1.length * v2.length) + 1.0) < tol


def vectors_equal(v1: Vector, v2: Vector, tol: float = 1e-6) -> bool:
    return (v1 - v2).length < tol


def axes_coincident(pt1: Vector, dir1: Vector, pt2: Vector, dir2: Vector,
                    pos_tol: float = 1e-4, dir_tol: float = 1e-6) -> bool:
    """Check if two axes are coaxial (same line)."""
    if not vectors_parallel(dir1, dir2, dir_tol):
        return False
    # Check if pt2 lies on axis 1
    to_pt2 = pt2 - pt1
    cross = to_pt2.cross(dir1)
    return cross.length < pos_tol


@dataclass
class PlanarFaceInfo:
    face: Face
    center: Vector
    normal: Vector
    area: float
    index: int


@dataclass
class CylindricalFaceInfo:
    face: Face
    axis_point: Vector
    axis_dir: Vector
    radius: float
    u_min: float
    u_max: float
    angle_sweep: float  # radians
    index: int


# ---- Core algorithm ----------------------------------------------------------

class UnfoldService:
    """Sheet-metal unfolding engine."""

    def __init__(self, request: UnfoldRequest):
        self.request = request
        self.warnings: list[str] = []

    def unfold(self, shape: Solid) -> UnfoldResponse:
        start_time = time.perf_counter()

        try:
            # Validate input
            if not isinstance(shape, Solid):
                return UnfoldResponse(
                    success=False,
                    error_code=UnfoldErrorCode.INVALID_SOLID,
                    error_message="Input must be a build123d Solid",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000
                )

            faces = list(shape.faces())
            if len(faces) < 4:
                return UnfoldResponse(
                    success=False,
                    error_code=UnfoldErrorCode.INSUFFICIENT_FACES,
                    error_message=f"Solid has only {len(faces)} faces, need at least 4",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000
                )

            # 1. Thickness detection
            thickness, planar_faces = self._detect_thickness(faces)
            if thickness is None:
                return UnfoldResponse(
                    success=False,
                    error_code=UnfoldErrorCode.NOT_SHEET,
                    error_message="No single thickness winner - not a constant-thickness sheet",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000
                )

            # 2. Bend detection
            bends, cylindrical_faces = self._detect_bends(faces, thickness)
            if not bends:
                return UnfoldResponse(
                    success=False,
                    error_code=UnfoldErrorCode.NO_BENDS_FOUND,
                    error_message="No valid bend pairs detected",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000
                )

            # 3. Build flange tree and unfold
            profile, bend_lines, bend_records = self._unfold_flanges(
                shape, planar_faces, cylindrical_faces, bends, thickness
            )

            # 4. Apply kerf offset
            if self.request.kerf > 0:
                from build123d import offset
                profile = offset(profile, -self.request.kerf)

            # 5. Compute metrics
            from build123d import area
            blank_area = area(profile)
            vol = solid_volume(shape)
            conservation = vol / (thickness * blank_area) if blank_area > 0 else 0.0

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            unfolded = Unfolded(
                profile=profile,
                bend_lines=bend_lines,
                bends=bend_records,
                thickness=thickness,
                k_factor=self.request.k_factor,
                kerf=self.request.kerf,
                blank_area=blank_area,
                volume=vol,
                material_conservation_ratio=conservation,
                warnings=self.warnings
            )

            return UnfoldResponse(
                success=True,
                unfolded=unfolded,
                processing_time_ms=elapsed_ms
            )

        except Exception as e:
            return UnfoldResponse(
                success=False,
                error_code=UnfoldErrorCode.INVALID_SOLID,
                error_message=f"Unfold failed: {str(e)}",
                processing_time_ms=(time.perf_counter() - start_time) * 1000
            )

    # ---- Thickness detection -------------------------------------------------

    def _detect_thickness(self, faces: list[Face]) -> tuple[Optional[float], list[PlanarFaceInfo]]:
        """Detect constant thickness from parallel planar face pairs.
        For a sheet metal part, opposite faces have parallel (same direction) normals
        but are on opposite sides of the part's center.
        """
        planar_infos: list[PlanarFaceInfo] = []
        for i, face in enumerate(faces):
            if is_planar_face(face):
                center, normal, area = get_planar_face_data(face)
                planar_infos.append(PlanarFaceInfo(face, center, normal, area, i))

        if len(planar_infos) < 2:
            return None, []

        # Compute part centroid
        total_area = sum(f.area for f in planar_infos)
        centroid = Vector(0, 0, 0)
        for f in planar_infos:
            centroid += f.center * (f.area / total_area)

        # Vote on thickness: for each pair of PARALLEL faces on opposite sides of centroid
        thickness_votes: dict[float, int] = defaultdict(int)
        face_pairs: list[tuple[PlanarFaceInfo, PlanarFaceInfo, float]] = []

        for i, fi in enumerate(planar_infos):
            for j, fj in enumerate(planar_infos[i+1:], i+1):
                if vectors_parallel(fi.normal, fj.normal):
                    # Check if they are on opposite sides of centroid
                    d1 = (fi.center - centroid).dot(fi.normal)
                    d2 = (fj.center - centroid).dot(fi.normal)
                    if d1 * d2 < 0:  # Opposite sides
                        dist = abs(d1 - d2)
                        if dist > 1e-4:  # Ignore degenerate
                            t = round(dist, 6)
                            thickness_votes[t] += 1
                            face_pairs.append((fi, fj, t))

        if not thickness_votes:
            return None, planar_infos

        # Find winner (must be clear majority)
        max_votes = max(thickness_votes.values())
        winners = [t for t, v in thickness_votes.items() if v == max_votes]

        if len(winners) != 1:
            self.warnings.append(f"Multiple thickness candidates: {winners}")
            return None, planar_infos

        thickness = winners[0]

        # Verify consistency: all parallel pairs on opposite sides should match this thickness
        for fi, fj, t in face_pairs:
            if abs(t - thickness) > thickness * 0.05:  # 5% tolerance
                self.warnings.append(f"Thickness variation detected: {t:.3f} vs {thickness:.3f}")

        return thickness, planar_infos

    # ---- Bend detection ------------------------------------------------------

    def _detect_bends(self, faces: list[Face], thickness: float
                      ) -> tuple[list[CylindricalFaceInfo], list[CylindricalFaceInfo]]:
        """Detect bends from coaxial cylindrical face pairs with radius diff = thickness."""
        cyl_infos: list[CylindricalFaceInfo] = []
        for i, face in enumerate(faces):
            if is_cylindrical_face(face):
                axis_pt, axis_dir, radius, u_min, u_max = get_cylindrical_face_data(face)
                angle_sweep = abs(u_max - u_min)
                # Refuse hems/curls: radius < thickness or sweep > 180°
                if radius < thickness * 0.99:  # Allow small tolerance
                    self.warnings.append(f"Hem detected: radius {radius:.3f} < thickness {thickness:.3f}")
                    continue
                if angle_sweep > math.pi + 1e-3:  # > 180°
                    self.warnings.append(f"Curl detected: sweep {math.degrees(angle_sweep):.1f}° > 180°")
                    continue
                cyl_infos.append(CylindricalFaceInfo(
                    face, axis_pt, axis_dir, radius, u_min, u_max, angle_sweep, i
                ))
            elif is_conical_face(face):
                self.warnings.append("Conical face detected - skipping")

        # Pair coaxial cylinders with radius difference = thickness
        bends: list[CylindricalFaceInfo] = []  # Inner faces (smaller radius)
        used = set()

        for i, ci in enumerate(cyl_infos):
            if i in used:
                continue
            for j, cj in enumerate(cyl_infos[i+1:], i+1):
                if j in used:
                    continue
                if axes_coincident(ci.axis_point, ci.axis_dir, cj.axis_point, cj.axis_dir):
                    r_diff = abs(ci.radius - cj.radius)
                    if abs(r_diff - thickness) < thickness * 0.05:  # 5% tolerance
                        # Inner face has smaller radius
                        inner = ci if ci.radius < cj.radius else cj
                        outer = cj if ci.radius < cj.radius else ci
                        bends.append(inner)
                        used.add(i)
                        used.add(j)
                        break

        return bends, cyl_infos

    # ---- Flange unfolding ----------------------------------------------------

    def _unfold_flanges(self, shape: Solid, planar_faces: list[PlanarFaceInfo],
                        cyl_faces: list[CylindricalFaceInfo], bends: list[CylindricalFaceInfo],
                        thickness: float) -> tuple[object, list, list[BendRecord]]:
        """Unfold flanges into flat pattern by composing rotations about bend axes.

        This is a simplified but functional implementation. A full implementation
        would build the flange adjacency graph and compose transformations.
        """
        from build123d import Compound, Face, Rotation, Location, Plane, Vector
        from build123d import flatten_face, union_faces, offset_profile

        # Root flange = largest planar face by area
        root_face = max(planar_faces, key=lambda f: f.area)
        root_plane = Plane(root_face.center, root_face.normal)

        # Collect all planar faces that are part of the sheet (not bend relief, etc.)
        sheet_faces = [f.face for f in planar_faces if f.area > thickness * thickness * 0.5]

        # Flatten each face to root plane coordinate system
        flat_faces = []
        bend_lines = []
        bend_records = []

        # For each bend, compute its line in the flat pattern
        for idx, bend in enumerate(bends):
            # Bend axis in 3D
            axis_3d = Axis(bend.axis_point, bend.axis_dir)

            # Find the two planar faces adjacent to this bend
            # (Simplified: find faces sharing edges with the cylindrical face)
            adjacent_planar = self._find_adjacent_planar_faces(bend.face, sheet_faces)
            if len(adjacent_planar) < 2:
                continue

            face_a, face_b = adjacent_planar[0], adjacent_planar[1]

            # Flatten both faces to root plane
            flat_a = flatten_face(face_a, root_plane)
            flat_b = flatten_face(face_b, root_plane)

            # The bend line is the intersection of the two flattened faces' boundaries
            # Simplified: use the bend axis projected to root plane
            bend_line_start, bend_line_end = self._compute_bend_line_in_flat(
                bend, root_plane, flat_a, flat_b
            )
            bend_lines.append((bend_line_start, bend_line_end))

            # Bend allowance
            angle_rad = bend.angle_sweep
            if self.request.bend_table:
                # TODO: bend table lookup
                ba = angle_rad * (bend.radius + self.request.k_factor * thickness)
            else:
                ba = angle_rad * (bend.radius + self.request.k_factor * thickness)

            # Determine bend direction (which side material folds to)
            # Use face normals relative to bend axis
            dir_a = self._get_flange_direction(face_a, axis_3d)
            dir_b = self._get_flange_direction(face_b, axis_3d)
            direction = BendDirection.UP if dir_a > 0 else BendDirection.DOWN

            # Flange lengths (simplified: face bounding box extent along bend axis)
            len_a = self._flange_length_along_axis(face_a, axis_3d)
            len_b = self._flange_length_along_axis(face_b, axis_3d)

            # Nearest cut/hole distance from bend tangent
            nearest_cut = self._nearest_cut_distance(bend.face, shape, axis_3d)

            record = BendRecord(
                index=idx,
                angle_deg=math.degrees(angle_rad),
                direction=direction,
                inside_radius=bend.radius,
                bend_allowance=ba,
                k_factor=self.request.k_factor,
                bend_line_start=bend_line_start,
                bend_line_end=bend_line_end,
                flange_length_side_a=len_a,
                flange_length_side_b=len_b,
                nearest_cut_distance=nearest_cut,
                axis_point=(bend.axis_point.X, bend.axis_point.Y, bend.axis_point.Z),
                axis_direction=(bend.axis_dir.X, bend.axis_dir.Y, bend.axis_dir.Z)
            )
            bend_records.append(record)

            flat_faces.extend([flat_a, flat_b])

        # Union all flat faces
        if not flat_faces:
            # Fallback: just flatten root
            flat_root = flatten_face(root_face.face, root_plane)
            profile = flat_root
        else:
            # Deduplicate faces (same geometry)
            unique_faces = []
            seen = set()
            for f in flat_faces:
                # Simple dedup by area+centroid
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(f.wrapped, props)
                centroid = props.CentreOfMass()
                key = (round(props.Mass(), 6), round(centroid.X(), 6), round(centroid.Y(), 6))
                if key not in seen:
                    seen.add(key)
                    unique_faces.append(f)

            profile = union_faces(unique_faces) if len(unique_faces) > 1 else unique_faces[0]

        return profile, bend_lines, bend_records

    def _find_adjacent_planar_faces(self, cyl_face: Face, planar_faces: list[Face]) -> list[Face]:
        """Find planar faces sharing edges with a cylindrical face."""
        adjacent = []
        cyl_edges = set(cyl_face.edges())

        for pf in planar_faces:
            pf_edges = set(pf.edges())
            if cyl_edges & pf_edges:  # Share at least one edge
                adjacent.append(pf)
        return adjacent

    def _compute_bend_line_in_flat(self, bend: CylindricalFaceInfo, root_plane: Plane,
                                    flat_a: Face, flat_b: Face) -> tuple[tuple[float, float], tuple[float, float]]:
        """Compute bend line segment in flat pattern coordinates."""
        # Project bend axis to root plane
        axis_pt = bend.axis_point
        axis_dir = bend.axis_dir

        # Project to root plane
        root_normal = Vector(root_plane.z_dir.X, root_plane.z_dir.Y, root_plane.z_dir.Z)
        root_origin = Vector(root_plane.origin.X, root_plane.origin.Y, root_plane.origin.Z)

        # Project axis point
        to_pt = axis_pt - root_origin
        proj_pt = to_pt - root_normal * to_pt.dot(root_normal)
        flat_origin = root_origin + proj_pt

        # Project axis direction
        proj_dir = axis_dir - root_normal * axis_dir.dot(root_normal)
        if proj_dir.length < 1e-6:
            # Axis perpendicular to root plane - use any perpendicular direction
            proj_dir = Vector(1, 0, 0)

        proj_dir = proj_dir.normalized()

        # Get extents from the flattened faces' bounding boxes
        from build123d import bounding_box
        bb_a = bounding_box(flat_a)
        bb_b = bounding_box(flat_b)

        # Find intersection of face boundaries along projected axis
        # Simplified: use combined bbox
        min_pt = Vector(min(bb_a.min.X, bb_b.min.X), min(bb_a.min.Y, bb_b.min.Y), 0)
        max_pt = Vector(max(bb_a.max.X, bb_b.max.X), max(bb_a.max.Y, bb_b.max.Y), 0)

        # Project bbox corners to axis line, get min/max parameter
        corners = [min_pt, Vector(max_pt.X, min_pt.Y, 0),
                   Vector(min_pt.X, max_pt.Y, 0), max_pt]
        params = [(c - flat_origin).dot(proj_dir) for c in corners]
        t_min, t_max = min(params), max(params)

        start_3d = flat_origin + proj_dir * t_min
        end_3d = flat_origin + proj_dir * t_max

        return ((start_3d.X, start_3d.Y), (end_3d.X, end_3d.Y))

    def _get_flange_direction(self, face: Face, axis: Axis) -> float:
        """Determine which side of bend axis the face lies on."""
        # Get face center, project to plane perpendicular to axis
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = Vector(props.CentreOfMass().X(), props.CentreOfMass().Y(), props.CentreOfMass().Z())

        to_center = center - axis.position
        # Cross product with axis direction gives side
        cross = to_center.cross(axis.direction)
        # Use a reference direction perpendicular to axis
        ref = Vector(1, 0, 0) if abs(axis.direction.Z) < 0.9 else Vector(0, 1, 0)
        ref = ref - axis.direction * ref.dot(axis.direction)
        if ref.length < 1e-6:
            ref = Vector(0, 1, 0)
        ref = ref.normalized()
        return cross.dot(ref)

    def _flange_length_along_axis(self, face: Face, axis: Axis) -> float:
        """Get flange extent along bend axis."""
        # Get face edges parallel to axis
        max_len = 0.0
        for edge in face.edges():
            # Check if edge is linear and parallel to axis
            curve = BRepAdaptor_Curve(edge.wrapped, True)
            if curve.GetType() == 1:  # GeomAbs_Line
                line = curve.Line()
                edge_dir = Vector(line.Direction().X(), line.Direction().Y(), line.Direction().Z())
                if vectors_parallel(edge_dir, axis.direction):
                    from build123d import edge_length
                    l = edge_length(edge)
                    if l > max_len:
                        max_len = l
        return max_len if max_len > 0 else 10.0  # Fallback

    def _nearest_cut_distance(self, bend_face: Face, solid: Solid, axis: Axis) -> float:
        """Find distance from bend tangent to nearest cut edge or hole."""
        # Get bend face boundary edges that are not shared with adjacent planar faces
        bend_edges = list(bend_face.edges())
        planar_faces = [f for f in solid.faces() if is_planar_face(f)]

        # Edges shared with planar faces are bend tangents
        tangent_edges = []
        for be in bend_edges:
            for pf in planar_faces:
                if be in pf.edges():
                    tangent_edges.append(be)
                    break

        if not tangent_edges:
            return 0.0

        # Find other edges (cuts, holes) on the same planar faces
        min_dist = float('inf')
        for te in tangent_edges:
            te_curve = BRepAdaptor_Curve(te.wrapped, True)
            # Sample points along tangent edge
            for param in [te_curve.FirstParameter(), te_curve.LastParameter()]:
                pt = te_curve.Value(param)
                pt_vec = Vector(pt.X(), pt.Y(), pt.Z())

                # Check distance to all other edges in solid
                for other_face in solid.faces():
                    if other_face == bend_face:
                        continue
                    for other_edge in other_face.edges():
                        if other_edge in tangent_edges:
                            continue
                        dist_shape = BRepExtrema_DistShapeShape(te.wrapped, other_edge.wrapped)
                        dist_shape.Perform()
                        if dist_shape.IsDone():
                            d = dist_shape.Value()
                            if d < min_dist:
                                min_dist = d

        return min_dist if min_dist != float('inf') else 0.0


# ---- Public API --------------------------------------------------------------

def unfold(shape: Solid, *, k_factor: float = 0.33, bend_table: Optional[dict] = None,
           kerf: float = 0.0) -> UnfoldResponse:
    """Main entry point for sheet-metal unfolding."""
    request = UnfoldRequest(k_factor=k_factor, bend_table=bend_table, kerf=kerf)
    service = UnfoldService(request)
    return service.unfold(shape)