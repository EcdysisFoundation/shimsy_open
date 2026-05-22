def convert_sample_type_abbrev_to_full(abbrev):
    mapping = {
        'sw': 'VegetationSweep',
        'qu': 'Quadrat'
    }
    return mapping.get(abbrev.lower(), abbrev)

def convert_sample_type_full_to_abbrev(sample_type):
    mapping = {
        'VegetationSweep': 'sw',
        'Quadrat': 'qu'
    }
    return mapping.get(sample_type, sample_type.lower()[:2])

def dish_number_from_folder(folder_name):
    """Dish index from folder prefix -> 4."""
    prefix = folder_name.split('_', 1)[0]
    return int(prefix) if prefix.isdigit() else 99


def parse_stitcher_sample_name(name):
    parts = name.split('_')
    
    if len(parts) < 3:
        return None
    
    site_number = parts[0]
    sample_type_abbrev = parts[1]
    transect = parts[2]
    
    sample_type = convert_sample_type_abbrev_to_full(sample_type_abbrev)
    
    return {
        'site_number': site_number[:4],
        'sample_type': sample_type,
        'transect': transect
    }

def filter_capture_points_by_dish(dish_number, manual_path_file=None):
    """
    Filter capture points from manual_path.json for a specific dish.

    Args:
        dish_number: String or int (1-6)
        manual_path_file: Path to manual_path.json (default: BASE_DIR/manual_path.json when in Django)

    Returns:
        dict with filtered capture_points and final_position
    """
    import json
    if manual_path_file is None:
        try:
            from django.conf import settings
            manual_path_file = str(settings.BASE_DIR / "manual_path.json")
        except Exception:
            import os
            manual_path_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manual_path.json")
    with open(manual_path_file) as f:
        path_data = json.load(f)
    
    dish_str = str(dish_number)
    filtered_points = [
        point for point in path_data['capture_points']
        if point.get('sample') == dish_str
    ]
    
    return {
        'final_position': path_data['final_position'],
        'capture_points': filtered_points
    }
