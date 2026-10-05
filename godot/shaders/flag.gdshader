shader_type spatial;
render_mode cull_disabled;

// Waving flag: displacement grows from the hoist (UV.x = 0) to the fly end.
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform float amplitude = 0.22;
uniform float wavelength = 1.6;
uniform float speed = 3.2;

void vertex() {
	float x = UV.x;
	float w = sin(x * 6.2831 / (wavelength / 3.0) * 0.5 - TIME * speed) * amplitude * x
		+ sin(x * 11.0 - TIME * speed * 1.7 + UV.y * 2.0) * amplitude * 0.35 * x;
	VERTEX += NORMAL * w;
	VERTEX.y -= x * x * 0.12;  // slight sag at the fly end
	float dw = cos(x * 6.2831 / (wavelength / 3.0) * 0.5 - TIME * speed) * amplitude;
	NORMAL = normalize(NORMAL - TANGENT * dw * x * 0.8);
}

void fragment() {
	vec4 c = texture(albedo_tex, UV);
	ALBEDO = c.rgb;
	ROUGHNESS = 0.85;
}
