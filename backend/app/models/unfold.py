"""Domain models for sheet-metal unfolding."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class BendDirection(str, Enum):
    """Direction of material fold relative to bend axis."""
    UP = "up"      # Material folds toward positive axis direction
    DOWN = "down"  # Material folds toward negative axis direction


class UnfoldErrorCode(str, Enum):
    """Standardized error codes for unfold failures."""
    NOT_SHEET = "NOT_SHEET"                    # No single thickness winner
    VARIABLE_THICKNESS = "VARIABLE_THICKNESS"  # Multiple thickness candidates
    NO_BENDS_FOUND = "NO_BENDS_FOUND"          # No valid bend pairs detected
    HEM_DETECTED = "HEM_DETECTED"              # Cylinder radius < thickness or sweep > 180°
    CONICAL_BEND = "CONICAL_BEND"              # Non-cylindrical or tapered bend face
    NON_PLANAR_BEND_FACE = "NON_PLANAR_BEND_FACE"  # Bend on non-planar adjacent face
    COLLISION_DETECTED = "COLLISION_DETECTED"  # Flanges intersect when unfolded
    INSUFFICIENT_FACES = "INSUFFICIENT_FACES"  # Not enough faces to classify
    INVALID_SOLID = "INVALID_SOLID"            # Not a valid build123d/OCCT solid


@dataclass(frozen=True)
class BendRecord:
    """Complete record for a single bend."""
    index: int
    angle_deg: float                 # Bend angle in degrees (inner face sweep)
    direction: BendDirection         # UP or DOWN
    inside_radius: float             # Inside bend radius (mm)
    bend_allowance: float            # BA = θ·(r + K·t) (mm)
    k_factor: float                  # K-factor used
    bend_line_start: tuple[float, float]  # Start point in flat pattern XY
    bend_line_end: tuple[float, float]    # End point in flat pattern XY
    flange_length_side_a: float      # Length of flange on one side (mm)
    flange_length_side_b: float      # Length of flange on other side (mm)
    nearest_cut_distance: float      # Distance from bend tangent to nearest cut/hole (mm)
    axis_point: tuple[float, float, float]  # Bend axis point in 3D
    axis_direction: tuple[float, float, float]  # Bend axis direction in 3D


@dataclass(frozen=True)
class Unfolded:
    """Result of unfolding a sheet-metal part."""
    profile: object                  # build123d Face/Compound - the flat blank
    bend_lines: list[tuple[tuple[float, float], tuple[float, float]]]  # [(start, end), ...]
    bends: list[BendRecord]          # Per-bend detailed records
    thickness: float                 # Detected sheet thickness (mm)
    k_factor: float                  # K-factor used
    kerf: float                      # Kerf offset applied (mm)
    blank_area: float                # Area of flat blank (mm²)
    volume: float                    # Original solid volume (mm³)
    material_conservation_ratio: float  # volume / (thickness * blank_area)
    warnings: list[str] = field(default_factory=list)  # Non-fatal issues


@dataclass(frozen=True)
class UnfoldRequest:
    """Input parameters for unfold operation."""
    k_factor: float = 0.33
    bend_table: Optional[dict] = None  # {thickness: {radius: {angle: deduction}}}
    kerf: float = 0.0
    bend_radius_threshold: float = 1e-3  # Min radius to consider as bend


@dataclass(frozen=True)
class UnfoldResponse:
    """API response for unfold operation."""
    success: bool
    unfolded: Optional[Unfolded] = None
    error_code: Optional[UnfoldErrorCode] = None
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0