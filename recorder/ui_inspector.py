from pywinauto import Desktop


def get_element_at(x: int, y: int) -> dict:
    element = Desktop(backend="uia").from_point(x, y)
    info = element.element_info
    return {
        "automation_id": info.automation_id,
        "name": info.name,
        "control_type": info.control_type,
        "class_name": info.class_name,
    }
