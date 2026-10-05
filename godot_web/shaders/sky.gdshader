shader_type sky;
render_mode use_debanding;

// Procedural daytime sky: horizon gradient, sun disk + halo from the scene's directional light,
// drifting fbm cumulus in the upper hemisphere. Night darkens everything and adds faint stars.
uniform vec3 zenith : source_color = vec3(0.30, 0.48, 0.80);
uniform vec3 horizon : source_color = vec3(0.78, 0.84, 0.90);
uniform vec3 ground : source_color = vec3(0.35, 0.36, 0.36);
uniform float day = 1.0;
uniform float cloud_cover = 0.48;
uniform float cloud_speed = 0.004;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
	float v = 0.0, a = 0.5;
	for (int k = 0; k < 6; k++) { v += a * noise(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
	return v;
}

void sky() {
	vec3 d = EYEDIR;
	float h = d.y;
	vec3 col = mix(horizon, zenith, pow(clamp(h, 0.0, 1.0), 0.55));
	if (h < 0.0) col = mix(horizon, ground, clamp(-h * 4.0, 0.0, 1.0));
	vec3 sd = LIGHT0_DIRECTION;
	float sun = max(dot(d, sd), 0.0);
	col += LIGHT0_COLOR * (pow(sun, 4000.0) * 40.0 + pow(sun, 12.0) * 0.25) * LIGHT0_ENERGY * day;
	if (h > 0.0) {
		vec2 uv = d.xz / (h + 0.12) * 1.2 + vec2(TIME * cloud_speed, TIME * cloud_speed * 0.4);
		float c = fbm(uv * 1.3);
		c = smoothstep(1.0 - cloud_cover, 1.0 - cloud_cover + 0.28, c);
		float shade = fbm(uv * 1.3 + sd.xz * 0.08);
		vec3 ccol = mix(vec3(1.0), vec3(0.72, 0.75, 0.8), smoothstep(0.4, 0.8, shade));
		ccol += LIGHT0_COLOR * pow(sun, 6.0) * 0.4;
		col = mix(col, ccol * mix(0.08, 1.0, day), c * smoothstep(0.0, 0.12, h));
	}
	if (day < 0.3 && h > 0.0) {
		float st = step(0.9975, hash(floor(d.xz / (h + 0.3) * 420.0)));
		col += vec3(st) * (0.3 - day) * 2.0;
	}
	COLOR = col * mix(0.04, 1.0, day);
}
