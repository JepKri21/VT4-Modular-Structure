"""
Test script for inventory_creator.py
Simulates user input to test instance generation.
"""

import sys
from io import StringIO
from inventory_creator import (
    create_inventory_items,
    get_next_instance_number,
    COMPONENT_REGISTRY,
)

def test_create_bottom_covers():
    """Test creating 2 Bottom Cover instances."""
    print("\n" + "=" * 70)
    print("TEST 1: Creating 2 Bottom Cover instances")
    print("=" * 70)
    
    component_type = "Bottom_Cover"
    quantity = 2
    config_values = {
        "Material": "ABS",
        "Color": "black",
        "Finish": "matte"
    }
    
    create_inventory_items(component_type, quantity, config_values)


def test_create_fuses():
    """Test creating 3 Fuse instances (no configuration)."""
    print("\n" + "=" * 70)
    print("TEST 2: Creating 3 Fuse instances (no config)")
    print("=" * 70)
    
    component_type = "Fuse"
    quantity = 3
    config_values = {}
    
    create_inventory_items(component_type, quantity, config_values)


def test_create_pcbs():
    """Test creating 2 PCB instances."""
    print("\n" + "=" * 70)
    print("TEST 3: Creating 2 PCB instances")
    print("=" * 70)
    
    component_type = "PCB"
    quantity = 2
    config_values = {}
    
    create_inventory_items(component_type, quantity, config_values)


def test_next_instance_numbers():
    """Test the next instance number detection."""
    print("\n" + "=" * 70)
    print("TEST 4: Checking next instance numbers")
    print("=" * 70)
    
    for comp_type in COMPONENT_REGISTRY.keys():
        next_num = get_next_instance_number(comp_type, COMPONENT_REGISTRY)
        print(f"{comp_type}: Next instance number = {next_num:03d}")


if __name__ == "__main__":
    try:
        test_create_bottom_covers()
        test_create_fuses()
        test_create_pcbs()
        test_next_instance_numbers()
        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 70)
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
