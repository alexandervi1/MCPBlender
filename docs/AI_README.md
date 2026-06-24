# Guía Para IA: Primer Uso De `blender-ai-mcp`

Este documento está escrito para un asistente de IA que ya tiene disponible el MCP `blender` y necesita usar Blender por primera vez a través de sus herramientas.

## Objetivo

Usa este MCP para controlar Blender de forma incremental y verificable: inspeccionar la escena, crear objetos, asignar materiales, configurar cámara/luces, preparar render, importar/exportar assets y ejecutar operaciones avanzadas cuando el usuario lo pida.

No asumas que Blender está listo. Antes de modificar la escena, confirma estado y conexión.

## Checklist Inicial

1. Llama a `get_scene_info`.
2. Llama a `list_objects`.
3. Si ambas herramientas fallan con error de conexión, indica al usuario que debe:
   - abrir Blender,
   - habilitar el addon **AI MCP Bridge**,
   - iniciar el servidor del addon en el puerto `9876`.
4. Si Blender responde, resume brevemente la escena actual antes de hacer cambios destructivos.

## Respuestas Esperadas

Todas las herramientas devuelven un sobre JSON.

Éxito:

```json
{
  "success": true,
  "result": {},
  "error": null
}
```

Error:

```json
{
  "success": false,
  "error": "ObjectNotFound",
  "message": "Object 'Cube' does not exist",
  "code": 404
}
```

Si recibes un error, no repitas la misma llamada sin cambiar algo. Corrige parámetros, inspecciona la escena o pide al usuario la acción necesaria.

## Primer Flujo Recomendado

Para crear una primera escena simple:

1. `get_scene_info`
2. `list_objects`
3. `create_object`
4. `create_material`
5. `assign_material`
6. `create_light`
7. `create_camera`
8. `point_camera_at`
9. `set_active_camera`
10. `set_render_engine`
11. `set_render_resolution`

## Pipeline Para Modelos 3D De Alta Calidad

Cuando el usuario pida un modelo profesional de cualquier cosa, usa este flujo:

1. **Entender el objetivo**: tipo de modelo, estilo, escala, vista principal y nivel de detalle.
2. **Referencias**: si hay imagen, usa `import_reference_image` o `setup_reference_planes`.
3. **Landmarks**: marca proporciones clave con `set_landmark`.
4. **Blockout**: crea volúmenes grandes con `create_primitive`, `create_rounded_box`, `create_tapered_cylinder` o `create_capsule_segment`.
5. **Estructura**: agrupa componentes con `create_component_group` y añade metadata con `set_object_metadata`.
6. **Refinamiento**: usa `boolean_operation`, `create_slot_cut`, `create_panel_seam`, `create_ring_joint`, `add_screw_array`, `add_vent_grille`.
7. **Acabado geométrico**: aplica `bevel_edges`, `add_support_loops` y `apply_weighted_normals`.
8. **Materiales**: usa `create_pbr_material`, `create_toon_material`, `create_procedural_material`, `assign_material_by_name`.
9. **Revisión**: usa `get_bounding_box`, `validate_scene_quality`, `validate_symmetry`, `generate_quality_report`.
10. **Iteración visual**: usa `render_orthographic_view` o render preview cuando sea necesario.

No saltes directo a detalles pequeños. Primero crea silueta y proporciones, luego componentes, después materiales y finalmente validación.

Ejemplo de intención de usuario:

```text
Crea una escena simple con un cubo rojo, luz de estudio y cámara lista para render.
```

Secuencia MCP sugerida:

```json
{"tool": "get_scene_info", "params": {}}
```

```json
{"tool": "list_objects", "params": {}}
```

```json
{
  "tool": "create_object",
  "params": {
    "object_type": "cube",
    "name": "HeroCube",
    "location": [0, 0, 1],
    "rotation": [0, 0, 0],
    "scale": [2, 2, 2]
  }
}
```

```json
{
  "tool": "create_material",
  "params": {
    "material_name": "HeroRed",
    "base_color": "#cc2222",
    "metallic": 0,
    "roughness": 0.45
  }
}
```

```json
{
  "tool": "assign_material",
  "params": {
    "object_name": "HeroCube",
    "material_name": "HeroRed"
  }
}
```

```json
{
  "tool": "create_light",
  "params": {
    "name": "KeyLight",
    "light_type": "AREA",
    "location": [3, -4, 5],
    "energy": 500,
    "color": "#ffffff"
  }
}
```

```json
{
  "tool": "create_camera",
  "params": {
    "name": "RenderCamera",
    "camera_type": "PERSP",
    "location": [4, -6, 4],
    "rotation": [1.1, 0, 0.55]
  }
}
```

```json
{
  "tool": "point_camera_at",
  "params": {
    "name": "RenderCamera",
    "target_object": "HeroCube"
  }
}
```

```json
{"tool": "set_active_camera", "params": {"name": "RenderCamera"}}
```

## Reglas De Uso Para La IA

- Para modelado libre, usa primero las herramientas `modeling_core` antes que scripts grandes.
- Piensa en componentes editables: `Objeto.Body`, `Objeto.Handle`, `Objeto.Panel_01`, `Objeto.Detail_01`.
- Usa `set_object_metadata` para marcar rol, asset padre, estilo y si una pieza es editable.
- Usa `get_bounding_box`, `snap_to_ground`, `align_objects` y `validate_model` después de crear varias piezas.
- Prefiere cambios pequeños y verificables sobre una llamada gigante.
- Después de crear, borrar, renombrar o importar objetos, usa `list_objects` o `get_object_info` para verificar.
- Antes de borrar (`delete_object`, `clear_scene`) confirma intención si el usuario no lo pidió explícitamente.
- Usa nombres claros y estables: `HeroCube`, `KeyLight`, `RenderCamera`, `StudioFloor`.
- Para colores, usa hex `"#RRGGBB"` o RGBA `[r, g, b, a]` con valores de `0` a `1`.
- Para vectores, usa listas `[x, y, z]`.
- No uses `execute_python` salvo que una herramienta específica no cubra la operación o el usuario pida scripting.
- Si usas `execute_python`, mantén el script corto, específico y con imports permitidos.
- Si una herramienta devuelve `ObjectNotFound`, llama a `list_objects` y corrige el nombre.
- Si una herramienta devuelve `InvalidParams`, revisa `docs/TOOLS.md` y corrige el payload.
- Si una herramienta devuelve `BlenderConnectionError`, el problema normalmente está en Blender/addon/puerto, no en la escena.

## Herramientas Principales Por Tarea

Modelado libre/profesional:

- `create_primitive`
- `create_curve_path`
- `create_pipe_along_path`
- `boolean_operation`
- `bevel_edges`
- `set_origin`
- `get_bounding_box`
- `snap_to_ground`
- `align_objects`
- `distribute_objects`
- `duplicate_along_axis`
- `create_component_group`
- `set_object_metadata`
- `find_objects`
- `validate_model`

Modelado con referencia:

- `import_reference_image`
- `setup_reference_planes`
- `set_landmark`
- `get_landmarks`
- `measure_between_landmarks`
- `align_object_to_landmarks`
- `calibrate_reference_scale`
- `render_orthographic_view`
- `compare_silhouette_bounds`

Hard-surface:

- `create_rounded_box`
- `create_tapered_cylinder`
- `create_capsule_segment`
- `create_panel_seam`
- `create_ring_joint`
- `create_slot_cut`
- `add_screw_array`
- `add_vent_grille`
- `apply_weighted_normals`
- `add_support_loops`

Materiales y acabado:

- `create_pbr_material`
- `create_toon_material`
- `create_procedural_material`
- `add_edge_wear`
- `assign_material_by_name`
- `create_decal`
- `add_outline_modifier`
- `apply_material_variation`

Calidad:

- `validate_scene_quality`
- `detect_overlaps`
- `validate_symmetry`
- `check_scale_consistency`
- `generate_quality_report`
- `suggest_model_improvements`

Inspección:

- `get_scene_info`
- `list_objects`
- `get_object_info`
- `list_materials`
- `list_lights`
- `list_collections`

Modelado básico:

- `create_object`
- `move_object`
- `rotate_object`
- `scale_object`
- `duplicate_object`
- `delete_object`
- `join_objects`
- `separate_object`

Materiales:

- `create_material`
- `assign_material`
- `set_material_color`
- `create_emission_material`
- `create_glass_material`
- `setup_pbr_material`

Cámara y luces:

- `create_camera`
- `point_camera_at`
- `set_active_camera`
- `create_light`
- `create_three_point_lighting`
- `create_hdri_lighting`

Render:

- `set_render_engine`
- `set_render_resolution`
- `set_render_output`
- `set_cycles_samples`
- `set_color_management`
- `render_image`

Import/export:

- `import_file`
- `export_file`
- `import_image_as_plane`
- `link_blend_file`
- `append_blend_file`

## Diagnóstico Rápido

Si no hay conexión:

```text
No puedo conectar con Blender. Abre Blender, activa el addon AI MCP Bridge, inicia el servidor en el panel AI MCP y confirma que usa localhost:9876.
```

Si falta un objeto:

```text
No encuentro ese objeto. Voy a listar los objetos disponibles y usar el nombre correcto.
```

Si una operación avanzada falla:

```text
La operación depende del contexto de Blender. Voy a inspeccionar el objeto/escena y aplicar una alternativa más directa.
```

## Referencias Internas

- `docs/TOOLS.md`: referencia completa de herramientas y parámetros.
- `docs/SETUP.md`: instalación por sistema operativo.
- `docs/README.md`: guía humana de instalación y uso.
- `mcp_config_example.json`: configuración lista para Claude Desktop.
