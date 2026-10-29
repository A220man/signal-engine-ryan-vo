#!/usr/bin/env python3
"""Quick test of unfold service with simple shapes."""
from build123d import Box, BuildPart, Circle, extrude, Plane
from app.services.unfold_service import unfold

# Test 1: Simple box (plate, no bends)
print("=== Test 1: Simple plate (10x10x2) ===")
plate = Box(10, 10, 2)
result1 = unfold(plate.solid(), k_factor=0.33)
print(f"Success: {result1.success}")
print(f"Error code: {result1.error_code}")
print(f"Error message: {result1.error_message}")
if result1.unfolded:
    print(f"Warnings: {result1.unfolded.warnings}")

print()

# Test 2: Cylinder (curl)
print("=== Test 2: Cylinder (curl, r=10, h=2) ===")
with BuildPart() as part:
    with BuildSketch(Plane.XY):
        Circle(10)
    extrude(amount=2)
result2 = unfold(part.part.solid(), k_factor=0.33)
print(f"Success: {result2.success}")
print(f"Error code: {result2.error_code}")
print(f"Error message: {result2.error_message}")
if result2.unfolded:
    print(f"Warnings: {result2.unfolded.warnings}")

print()

# Test 3: Box with one bend - try to create a simple L-bracket
print("=== Test 3: L-bracket attempt ===")
from build123d import BuildPart, BuildSketch, Rectangle, Plane, extrude, fillet, Edge
with BuildPart() as part:
    # Base flange
    with BuildSketch(Plane.XY):
        Rectangle(50, 30)
    extrude(amount=2)
    # Add a bend by creating a cylindrical face... this is hard with build123d
    # Let's try using a fillet on an edge
    # Actually, build123d doesn't easily create proper sheet metal bends
    pass
result3 = unfold(part.part.solid(), k_factor=0.33)
print(f"Success: {result3.success}")
print(f"Error code: {result3.error_code}")
print(f"Error message: {result3.error_message}")
if result3.unfolded:
    print(f"Thickness: {result3.unfolded.thickness}")
    print(f"Bends: {len(result3.unfolded.bends)}")
    print(f"Warnings: {result3.unfolded.warnings}")

