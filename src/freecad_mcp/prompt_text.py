ASSET_CREATION_STRATEGY = """
Asset Creation Strategy for FreeCAD MCP

When creating content in FreeCAD, always follow these steps:

0. Before starting any task, always use get_objects() to confirm the current state of the document.

1. Utilize the parts library:
   - Check available parts using get_parts_list().
   - If the required part exists in the library, use insert_part_from_library() to insert it into your document.

2. If the appropriate asset is not available in the parts library:
   - Create basic shapes (e.g., cubes, cylinders, spheres) using create_object().
   - Adjust and define detailed properties of the shapes as necessary using edit_object().

3. Always assign clear and descriptive names to objects when adding them to the document.

4. Explicitly set the position, scale, and rotation properties of created or inserted objects using edit_object() to ensure proper spatial relationships.

5. After editing an object, always verify that the set properties have been correctly applied by using get_object().

6. If detailed customization or specialized operations are necessary, use execute_code() to run custom Python scripts.

7. Manage screenshot feedback to save tokens. Tools that modify or inspect the
   model accept optional `include_screenshot` and `view_name` parameters:
   - Pass include_screenshot=False when the image would not be informative:
     analytical or computational scripts whose result is printed output,
     bulk property edits, or intermediate steps in a longer sequence of
     changes where only the final state needs visual confirmation.
   - Pass view_name (e.g. "Front", "Top", "Right") to orient the screenshot
     toward the part of the model you changed; the default is "Isometric" (top-front-right).
   - When you skipped screenshots during intermediate steps, use get_view()
     afterwards to visually inspect the result from the most informative angle.

Only revert to basic creation methods in the following cases:
- When the required asset is not available in the parts library.
- When a basic shape is explicitly requested.
- When creating complex shapes requires custom scripting.
"""
