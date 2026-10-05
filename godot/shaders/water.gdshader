shader_type spatial;
render_mode cull_disabled;

// Calm water: two scrolling ripple normal maps, sky reflection via low roughness, fresnel-tinted depth colour.
uniform vec3 deep_color : source_color = vec3(0.07, 0.11, 0.11);
uniform vec3 shallow_color : source_color = vec3(0.22, 0.30, 0.28);
uniform sampler2D ripple_a : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D ripple_b : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float scale = 1.6;
uniform float speed = 0.05;
uniform float strength = 0.55;

void fragment() {
	vec2 wuv = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xz / scale;
	vec3 na = texture(ripple_a, wuv + vec2(TIME * speed, TIME * speed * 0.6)).xyz * 2.0 - 1.0;
	vec3 nb = texture(ripple_b, wuv * 1.7 - vec2(TIME * speed * 0.8, -TIME * speed * 0.3)).xyz * 2.0 - 1.0;
	NORMAL_MAP = normalize(vec3(na.xy + nb.xy, na.z * nb.z)) * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = strength;
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALBEDO = mix(shallow_color, deep_color, fres);
	ROUGHNESS = 0.06;
	METALLIC = 0.0;
	SPECULAR = 0.6;
}
