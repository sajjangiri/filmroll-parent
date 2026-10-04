/**
 * Live film-look preview. The shader runs on a WebGL canvas only; capture still
 * reads the raw <video> frame so originals stay clean in storage.
 */

const VERTEX_SHADER = `
  attribute vec2 a_position;
  attribute vec2 a_texCoord;
  varying vec2 v_texCoord;
  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    v_texCoord = a_texCoord;
  }
`;

const FRAGMENT_SHADER = `
  precision mediump float;
  varying vec2 v_texCoord;
  uniform sampler2D u_video;
  uniform float u_mirror;
  void main() {
    vec2 tc = v_texCoord;
    if (u_mirror > 0.5) {
      tc.x = 1.0 - tc.x;
    }
    vec4 color = texture2D(u_video, tc);
    vec3 c = color.rgb;
    float luma = dot(c, vec3(0.299, 0.587, 0.114));
    c = mix(vec3(luma), c, 0.88);
    c.r *= 1.05;
    c.g *= 1.01;
    c.b *= 0.92;
    c = (c - 0.5) * 1.06 + 0.5;
    vec2 uv = v_texCoord - 0.5;
    float vig = 1.0 - dot(uv, uv) * 1.1;
    c *= clamp(vig, 0.5, 1.0);
    gl_FragColor = vec4(clamp(c, 0.0, 1.0), color.a);
  }
`;

function compileShader(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("Could not create shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader) ?? "shader compile failed";
    gl.deleteShader(shader);
    throw new Error(log);
  }
  return shader;
}

function createProgram(gl: WebGLRenderingContext): WebGLProgram {
  const program = gl.createProgram();
  if (!program) throw new Error("Could not create program");
  const vert = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const frag = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  gl.attachShader(program, vert);
  gl.attachShader(program, frag);
  gl.linkProgram(program);
  gl.deleteShader(vert);
  gl.deleteShader(frag);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program) ?? "program link failed";
    gl.deleteProgram(program);
    throw new Error(log);
  }
  return program;
}

export type FilmPreviewHandle = {
  stop: () => void;
};

/** Draw the video through the film shader until stop() is called. */
export function startFilmPreview(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  mirror: boolean,
): FilmPreviewHandle | null {
  const gl = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    preserveDrawingBuffer: false,
  });
  if (!gl) return null;
  const context = gl;

  const program = createProgram(context);
  context.useProgram(program);

  const positionLoc = context.getAttribLocation(program, "a_position");
  const texCoordLoc = context.getAttribLocation(program, "a_texCoord");
  const mirrorLoc = context.getUniformLocation(program, "u_mirror");
  const videoLoc = context.getUniformLocation(program, "u_video");

  const positions = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
  const texCoords = new Float32Array([0, 1, 1, 1, 0, 0, 1, 0]);

  const posBuffer = context.createBuffer();
  const texBuffer = context.createBuffer();
  if (!posBuffer || !texBuffer) return null;

  context.bindBuffer(context.ARRAY_BUFFER, posBuffer);
  context.bufferData(context.ARRAY_BUFFER, positions, context.STATIC_DRAW);
  context.enableVertexAttribArray(positionLoc);
  context.vertexAttribPointer(positionLoc, 2, context.FLOAT, false, 0, 0);

  context.bindBuffer(context.ARRAY_BUFFER, texBuffer);
  context.bufferData(context.ARRAY_BUFFER, texCoords, context.STATIC_DRAW);
  context.enableVertexAttribArray(texCoordLoc);
  context.vertexAttribPointer(texCoordLoc, 2, context.FLOAT, false, 0, 0);

  const texture = context.createTexture();
  if (!texture) return null;
  context.activeTexture(context.TEXTURE0);
  context.bindTexture(context.TEXTURE_2D, texture);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_S, context.CLAMP_TO_EDGE);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_T, context.CLAMP_TO_EDGE);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.LINEAR);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.LINEAR);
  context.uniform1i(videoLoc, 0);
  context.uniform1f(mirrorLoc, mirror ? 1 : 0);

  let frame = 0;
  let stopped = false;

  function draw() {
    if (stopped) return;
    frame = requestAnimationFrame(draw);

    if (video.readyState < video.HAVE_CURRENT_DATA) return;

    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) return;

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      context.viewport(0, 0, width, height);
    }

    context.bindTexture(context.TEXTURE_2D, texture);
    context.texImage2D(
      context.TEXTURE_2D,
      0,
      context.RGBA,
      context.RGBA,
      context.UNSIGNED_BYTE,
      video,
    );
    context.drawArrays(context.TRIANGLE_STRIP, 0, 4);
  }

  draw();

  return {
    stop() {
      stopped = true;
      cancelAnimationFrame(frame);
      context.deleteTexture(texture);
      context.deleteBuffer(posBuffer);
      context.deleteBuffer(texBuffer);
      context.deleteProgram(program);
    },
  };
}
