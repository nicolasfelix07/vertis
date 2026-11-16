---VERTEX SHADER-------------------------------------------------------
// PIPELINE GRÁFICO — etapa 1: VERTEX SHADER (roda uma vez por VÉRTICE, na placa de vídeo)
// Aplica as MESMAS matrizes que montamos em Python (cg/transformacoes.py):
//   posição na tela = projeção · vista · modelo · vértice
#ifdef GL_ES
    precision highp float;
#endif
attribute vec3 v_pos;
attribute vec3 v_normal;
attribute vec3 v_cor;

uniform mat4 modelo;
uniform mat4 vista;
uniform mat4 projecao;
uniform mat4 normal_mat;
uniform vec3 luz;
uniform float por_pixel;

varying vec3 n_v;
varying vec3 p_v;
varying vec3 c_v;
varying vec3 gouraud;

vec3 iluminar(vec3 N, vec3 P, vec3 cor) {
    // Modelo de Blinn-Phong: ambiente + difusa (N·L) + especular (N·H)^n
    vec3 L = normalize(luz);
    vec3 V = normalize(-P);
    vec3 H = normalize(L + V);
    float difusa = max(dot(N, L), 0.0);
    float especular = pow(max(dot(N, H), 0.0), 40.0) * 0.55;
    return cor * (0.30 + 0.75 * difusa) + vec3(especular);
}

void main(void) {
    vec4 p = vista * modelo * vec4(v_pos, 1.0);
    p_v = p.xyz;
    n_v = normalize((normal_mat * vec4(v_normal, 0.0)).xyz);
    c_v = v_cor;
    // GOURAUD: a cor é calculada aqui, nos vértices, e depois só interpolada
    gouraud = iluminar(n_v, p_v, v_cor);
    gl_Position = projecao * p;
}

---FRAGMENT SHADER-----------------------------------------------------
// PIPELINE GRÁFICO — etapa 2: FRAGMENT SHADER (roda uma vez por PIXEL)
// Depois dele, o Z-BUFFER compara a profundidade e só deixa passar
// o pixel que está mais perto da câmera.
#ifdef GL_ES
    precision highp float;
#endif
uniform vec3 luz;
uniform float por_pixel;

varying vec3 n_v;
varying vec3 p_v;
varying vec3 c_v;
varying vec3 gouraud;

void main(void) {
    if (por_pixel > 0.5) {
        // PHONG: a normal é interpolada e a luz é calculada em CADA pixel (brilho mais preciso)
        vec3 N = normalize(n_v);
        vec3 L = normalize(luz);
        vec3 V = normalize(-p_v);
        vec3 H = normalize(L + V);
        float difusa = max(dot(N, L), 0.0);
        float especular = pow(max(dot(N, H), 0.0), 40.0) * 0.55;
        gl_FragColor = vec4(c_v * (0.30 + 0.75 * difusa) + vec3(especular), 1.0);
    } else {
        gl_FragColor = vec4(gouraud, 1.0);
    }
}
