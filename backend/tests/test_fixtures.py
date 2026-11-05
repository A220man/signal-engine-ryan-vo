"""Test fixtures for sheet metal unfold tests."""
from __future__ import annotations
from build123d import *
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder
from typing import Optional
from collections import defaultdict
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp


def create_l_bracket(
    base_width: float = 50.0,
    base_depth: float = 10.0,
    thickness: float = 2.0,
    flange_height: float = 10.0,
    bend_radius: float = 1.0,
) -> Solid:
    """Create an L-bracket with proper sheet metal bends using a single BuildPart with fillets."""
    with BuildPart() as part:
        # Base flange
        with BuildSketch(Plane.XY):
            Rectangle(base_width, base_depth)
        extrude(amount=thickness)
        
        # Vertical flange on +Y side
        front_face = part.faces().sort_by(Axis.Y)[-1]
        with BuildSketch(front_face):
            Rectangle(base_width, flange_height)
        extrude(amount=flange_height)
        
        # Apply fillets to create bends - do both inner and outer in one go
        solid = part.part.solid()
        
        # Find ALL bend edges (inner and outer) before any filleting
        bend_edges = []
        for e in solid.edges():
            c = e.center()
            # Inner bend: Y=base_depth, Z=thickness
            if abs(c.Y - base_depth) < 0.01 and abs(c.Z - thickness) < 0.01 and abs(e.length - base_width) < 0.01:
                bend_edges.append(('inner', e))
            # Outer bend: Y=base_depth, Z=thickness + flange_height
            if abs(c.Y - base_depth) < 0.01 and abs(c.Z - (thickness + flange_height)) < 0.01 and abs(e.length - base_width) < 0.01:
                bend_edges.append(('outer', e))
        
        print(f"Found {len(bend_edges)} bend edges before fillet")
        for typ, e in bend_edges:
            c = e.center()
            print(f"  {typ}: center=({c.X:.2f},{c.Y:.2f},{c.Z:.2f}), len={e.length:.2f}")
        
        # Fillet inner edges first (smaller radius)
        inner_edges = [e for typ, e in bend_edges if typ == 'inner']
        if inner_edges:
            fillet(inner_edges, radius=bend_radius)
        
        solid = part.part.solid()
        
        # Re-find outer edges after inner fillet
        outer_edges = []
        for e in solid.edges():
            c = e.center()
            if abs(c.Y - base_depth) < 0.01 and abs(c.Z - (thickness + flange_height)) < 0.01 and abs(e.length - base_width) < 0.01:
                outer_edges.append(e)
        
        print(f"Found {len(outer_edges)} outer bend edges after inner fillet")
        for e in outer_edges:
            c = e.center()
            print(f"  outer: center=({c.X:.2f},{c.Y:.2f},{c.Z:.2f}), len={e.length:.2f}")
        
        if outer_edges:
            fillet(outer_edges, radius=bend_radius + thickness)
    
    return part.part.solid()


def create_u_channel(
    base_width: float = 50.0,
    base_depth: float = 10.0,
    thickness: float = 2.0,
    flange_height: float = 10.0,
    bend_radius: float = 1.0,
) -> Solid:
    """Create a U-channel (base + two flanges) with proper sheet metal bends."""
    with BuildPart() as part:
        # Base flange
        with BuildSketch(Plane.XY):
            Rectangle(base_width, base_depth)
        extrude(amount=thickness)
        
        # Front flange (+Y)
        front_face = part.faces().sort_by(Axis.Y)[-1]
        with BuildSketch(front_face):
            Rectangle(base_width, flange_height)
        extrude(amount=flange_height)
        
        # Back flange (-Y)
        back_face = part.faces().sort_by(Axis.Y)[0]
        with BuildSketch(back_face):
            Rectangle(base_width, flange_height)
        extrude(amount=-flange_height)
        
        solid = part.part.solid()
        
        # Find all bend edges
        for bend_y in [base_depth, -base_depth]:
            # Inner edges
            inner_edges = [
                e for e in solid.edges()
                if abs(e.center().Y - bend_y) < 0.01
                and abs(e.center().Z - thickness) < 0.01
                and abs(e.length - base_width) < 0.01
            ]
            if inner_edges:
                fillet(inner_edges, radius=bend_radius)
        
        solid = part.part.solid()
        
        # Outer edges
        for bend_y in [base_depth, -base_depth]:
            outer_edges = [
                e for e in solid.edges()
                if abs(e.center().Y - bend_y) < 0.01
                and abs(e.center().Z - (thickness + flange_height)) < 0.01
                and abs(e.length - base_width) < 0.01
            ]
            if outer_edges:
                fillet(outer_edges, radius=bend_radius + thickness)
    
    return part.part.solid()


def create_variable_thickness_part() -> Solid:
    """Create a part with variable thickness (tapered) for refusal testing."""
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            Rectangle(10, 10)
        extrude(amount=2, taper=15)
    return part.part.solid()


def create_curl_part() -> Solid:
    """Create a near-closed cylinder (curl > 180° sweep) for refusal testing."""
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            Circle(10)
        extrude(amount=2)
    return part.part.solid()


def create_conical_bend_part() -> Solid:
    """Create a part with a conical bend face for refusal testing."""
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            Rectangle(50, 10)
        extrude(amount=2)
        front_face = part.faces().sort_by(Axis.Y)[-1]
        with BuildSketch(front_face):
            Rectangle(50, 10)
        extrude(amount=10, taper=45)
    return part.part.solid()


# ---- Verification helpers ----

def face_surface_type(face: Face) -> int:
    surf = BRepAdaptor_Surface(face.wrapped, True)
    return surf.GetType()

def is_planar_face(face: Face) -> bool:
    return face_surface_type(face) == GeomAbs_Plane

def is_cylindrical_face(face: Face) -> bool:
    return face_surface_type(face) == GeomAbs_Cylinder

def get_planar_face_data(face: Face) -> tuple[Vector, Vector, float]:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, props)
    center = Vector(props.CentreOfMass().X(), props.CentreOfMass().Y(), props.CentreOfMass().Z())
    surf = BRepAdaptor_Surface(face.wrapped, True)
    plane = surf.Plane()
    normal = Vector(plane.Axis().Direction().X(), plane.Axis().Direction().Y(), plane.Axis().Direction().Z())
    area = props.Mass()
    return center, normal, area

def get_cylindrical_face_data(face: Face) -> tuple[Vector, Vector, float, float, float]:
    surf = BRepAdaptor_Surface(face.wrapped, True)
    cylinder = surf.Cylinder()
    axis_point = Vector(cylinder.Axis().Location().X(), cylinder.Axis().Location().Y(), cylinder.Axis().Location().Z())
    axis_dir = Vector(cylinder.Axis().Direction().X(), cylinder.Axis().Direction().Y(), cylinder.Axis().Direction().Z())
    radius = cylinder.Radius()
    u_min, u_max = surf.FirstUParameter(), surf.LastUParameter()
    return axis_point, axis_dir, radius, u_min, u_max

def vectors_parallel(v1: Vector, v2: Vector, tol: float = 1e-6) -> bool:
    return abs(v1.dot(v2) / (v1.length * v2.length) - 1.0) < tol

def axes_coincident(pt1: Vector, dir1: Vector, pt2: Vector, dir2: Vector,
                    pos_tol: float = 1e-4, dir_tol: float = 1e-6) -> bool:
    if not vectors_parallel(dir1, dir2, dir_tol):
        return False
    cross = (pt2 - pt1).cross(dir1)
    return cross.length < pos_tol


def verify_sheet_metal(solid: Solid) -> dict:
    faces = list(solid.faces())
    
    planar_infos = []
    for i, face in enumerate(faces):
        if is_planar_face(face):
            center, normal, area = get_planar_face_data(face)
            planar_infos.append((center, normal, area, i))
    
    if len(planar_infos) < 2:
        return {"thickness": None, "num_cyl_pairs": 0, "is_valid": False}
    
    total_area = sum(p[2] for p in planar_infos)
    centroid = Vector(0, 0, 0)
    for center, normal, area, _ in planar_infos:
        centroid += center * (area / total_area)
    
    thickness_votes = defaultdict(float)
    for i, (ci, ni, ai, _) in enumerate(planar_infos):
        for j, (cj, nj, aj, _) in enumerate(planar_infos[i+1:], i+1):
            if vectors_parallel(ni, nj):
                d1 = (ci - centroid).dot(ni)
                d2 = (cj - centroid).dot(ni)
                if d1 * d2 < 0:
                    dist = abs(d1 - d2)
                    if dist > 1e-4:
                        t = round(dist, 6)
                        weight = min(ai, aj)
                        thickness_votes[t] += weight
    
    if not thickness_votes:
        return {"thickness": None, "num_cyl_pairs": 0, "is_valid": False}
    
    max_weight = max(thickness_votes.values())
    winners = [t for t, w in thickness_votes.items() if abs(w - max_weight) < 1e-6]
    thickness = winners[0] if len(winners) == 1 else None
    
    cyl_infos = []
    for i, face in enumerate(faces):
        if is_cylindrical_face(face):
            axis_pt, axis_dir, radius, u_min, u_max = get_cylindrical_face_data(face)
            angle_sweep = abs(u_max - u_min)
            cyl_infos.append((axis_pt, axis_dir, radius, angle_sweep, i))
    
    num_pairs = 0
    used = set()
    if thickness:
        for i, (pt1, dir1, r1, sweep1, _) in enumerate(cyl_infos):
            if i in used:
                continue
            for j, (pt2, dir2, r2, sweep2, _) in enumerate(cyl_infos[i+1:], i+1):
                if j in used:
                    continue
                if axes_coincident(pt1, dir1, pt2, dir2):
                    r_diff = abs(r1 - r2)
                    if abs(r_diff - thickness) < thickness * 0.05:
                        num_pairs += 1
                        used.add(i)
                        used.add(j)
                        break
    
    return {
        "thickness": thickness,
        "num_cyl_pairs": num_pairs,
        "is_valid": thickness is not None and num_pairs > 0,
        "num_planar": len(planar_infos),
        "num_cylindrical": len(cyl_infos)
    }


if __name__ == "__main__":
    print("Testing L-bracket...")
    l_bracket = create_l_bracket()
    result = verify_sheet_metal(l_bracket)
    print(f"  {result}")
    
    print("Testing U-channel...")
    u_channel = create_u_channel()
    result = verify_sheet_metal(u_channel)
    print(f"  {result}")
    
    print("Testing variable thickness...")
    var = create_variable_thickness_part()
    result = verify_sheet_metal(var)
    print(f"  {result}")
    
    print("Testing curl...")
    curl = create_curl_part()
    result = verify_sheet_metal(curl)
    print(f"  {result}")
