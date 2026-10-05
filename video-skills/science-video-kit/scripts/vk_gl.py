"""vk_gl - minimal headless moderngl harness for ray-marched / shader-driven looks.

    R = GL(1920, 1080)
    R.load('world', open('glsl/world.glsl').read())          # your fragment shader (see contract below)
    img = R.render('world', lambda ts: dict(uTime=ts, uCam=...), t, spp=6, shutter=0.5, fps=30,
                   post=dict(exposure=1.0, bloom=0.6, bloom_thr=1.0, sat=1.05, contrast=1.05, vignette=0.35,
                             grain=0.03, flash=0.0, fade=1.0, ca=0.0))   # -> uint8 HxWx3

Fragment shader contract (#version 430 is prepended, plus COMMON below):
    uniform vec2 uRes; uniform vec2 uJitter;  uniform vec2 uLens; uniform float uSeed;  out vec4 o;
    write linear HDR rgb to o.rgb (alpha ignored). Pixel = gl_FragCoord.xy + uJitter.
Samples: additive accumulation of `spp` jittered passes (Halton 2,3 subpixel, Halton 5,7 lens disc for DoF).
    With shutter > 0 each pass gets its own sub-frame time -> real motion blur.
    Sample pattern is the SAME every frame (noise stays put instead of crawling).
NaN/Inf guard: the resolve pass zeroes non-finite pixels and clamps to 6e4. One NaN pixel otherwise gets smeared by the
    mip bloom into flickering black squares - keep the guard, also guard inside heavy shaders.
tiles > 1 renders horizontal strips with ctx.finish() between (avoids Windows GPU TDR timeouts on heavy shaders).
Overlay 2D text with vk_core: build a vk_core.Canvas, draw only text/shapes, then composite (see SKILL.md).
"""
import numpy as np
import moderngl

VS = """#version 430
in vec2 in_pos; void main(){ gl_Position = vec4(in_pos, 0., 1.); }"""

COMMON = """
uniform vec2 uRes; uniform vec2 uJitter; uniform vec2 uLens; uniform float uSeed; uniform vec4 uRegion;
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * .1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
vec3 camRay(vec2 frag, vec3 R, vec3 U, vec3 F, float tanh_){
    vec2 q = (2. * frag - uRes) / uRes.y; return normalize(F + (q.x * R + q.y * U) * tanh_); }
"""

RESOLVE = """#version 430
uniform sampler2D uAcc; uniform float uInv; out vec4 o;
void main(){ vec4 v = texelFetch(uAcc, ivec2(gl_FragCoord.xy), 0) * uInv;
  if(any(isnan(v)) || any(isinf(v))) v = vec4(0.); o = clamp(v, 0., 6e4); }"""

POST = """#version 430
uniform sampler2D uHdr; uniform vec2 uRes; uniform float uExposure, uBloom, uBloomThr, uSat, uContrast, uVignette,
  uGrain, uFlash, uFade, uCA, uSeed; out vec4 o;
vec3 blurLod(vec2 uv, float lod){ vec2 px = exp2(lod) / uRes; vec3 c = vec3(0.);
  for(int i=-1;i<=1;i++) for(int j=-1;j<=1;j++) c += textureLod(uHdr, uv + vec2(i,j) * px, lod).rgb; return c / 9.; }
vec3 aces(vec3 x){ return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14), 0., 1.); }
float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233)) + uSeed) * 43758.5453); }
void main(){
  vec2 uv = gl_FragCoord.xy / uRes;
  vec3 c;
  if(uCA > 0.){ vec2 d = (uv - .5) * uCA / uRes.x;
    c = vec3(texture(uHdr, uv + d).r, texture(uHdr, uv).g, texture(uHdr, uv - d).b); }
  else c = texture(uHdr, uv).rgb;
  vec3 b = blurLod(uv, 1.5) * .25 + blurLod(uv, 3.) * .3 + blurLod(uv, 4.5) * .25 + blurLod(uv, 6.) * .2;
  c += max(b - uBloomThr, 0.) * uBloom + b * uBloom * .12;
  c = c * uExposure + uFlash;
  c = aces(c);
  c = pow(c, vec3(1. / 2.2));
  float l = dot(c, vec3(.2126, .7152, .0722));
  c = mix(vec3(l), c, uSat);
  c = (c - .5) * uContrast + .5;
  vec2 q = uv - .5; c *= 1. - uVignette * dot(q, q) * 2.2;
  c += (h(gl_FragCoord.xy) - .5) * uGrain;
  o = vec4(clamp(c * uFade, 0., 1.), 1.);
}"""


def halton(i, b):
    f, r = 1.0, 0.0
    while i > 0:
        f /= b
        r += f * (i % b)
        i //= b
    return r


def look_at(pos, target, fov_deg=40, roll=0.0):
    pos, target = np.asarray(pos, float), np.asarray(target, float)
    F = target - pos
    F /= np.linalg.norm(F)
    up = np.array([np.sin(roll), np.cos(roll), 0.0])
    R = np.cross(F, up)
    R /= np.linalg.norm(R)
    U = np.cross(R, F)
    return dict(uCamPos=tuple(pos), uCamR=tuple(R), uCamU=tuple(U), uCamF=tuple(F), uTanH=float(np.tan(np.radians(fov_deg) / 2)))


def project(cam, P, W, H):
    """world point -> screen px (for placing 2D labels over 3D objects)"""
    d = np.asarray(P, float) - np.asarray(cam['uCamPos'])
    z = d @ np.asarray(cam['uCamF'])
    if z <= 1e-4:
        return None
    x = (d @ np.asarray(cam['uCamR'])) / (z * cam['uTanH'])
    y = (d @ np.asarray(cam['uCamU'])) / (z * cam['uTanH'])
    return (W / 2 + x * H / 2, H / 2 - y * H / 2)


class GL:
    def __init__(self, W=1920, H=1080, tiles=1):
        self.W, self.H, self.tiles = W, H, tiles
        self.ctx = moderngl.create_standalone_context(require=430)
        self.vbo = self.ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], 'f4').tobytes())
        self.acc = self.ctx.texture((W, H), 4, dtype='f4')
        self.acc_fbo = self.ctx.framebuffer([self.acc])
        self.hdr = self.ctx.texture((W, H), 4, dtype='f2')
        self.hdr.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        self.hdr_fbo = self.ctx.framebuffer([self.hdr])
        self.out = self.ctx.texture((W, H), 4)
        self.out_fbo = self.ctx.framebuffer([self.out])
        self.progs, self.vaos = {}, {}
        self._add('_resolve', RESOLVE)
        self._add('_post', POST)

    def _add(self, name, frag):
        p = self.ctx.program(vertex_shader=VS, fragment_shader=frag)
        self.progs[name] = p
        self.vaos[name] = self.ctx.vertex_array(p, [(self.vbo, '2f', 'in_pos')])

    def load(self, name, frag_body):
        """frag_body: shader WITHOUT #version; COMMON is prepended."""
        self._add(name, '#version 430\n' + COMMON + '\n' + frag_body)

    @staticmethod
    def _set(prog, k, v):
        if k not in prog or not isinstance(prog[k], moderngl.Uniform):
            return
        if isinstance(v, (int, float, np.floating)):
            prog[k].value = float(v)
        elif isinstance(v, bytes):
            prog[k].write(v)
        else:
            prog[k].value = tuple(float(x) for x in v)

    def render(self, name, uniforms_fn, t, spp=4, shutter=0.0, fps=30, post=None, textures=None):
        p, vao = self.progs[name], self.vaos[name]
        self.acc_fbo.use()
        self.acc_fbo.clear(0, 0, 0, 0)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE
        for k, tex in enumerate(textures or []):
            tex.use(k + 1)
        for i in range(spp):
            j = i + 1
            ts = t + (halton(j, 11) - 0.5) * shutter / fps if shutter > 0 else t
            u = dict(uniforms_fn(ts))
            u.update(uRes=(self.W, self.H), uJitter=(halton(j, 2) - 0.5, halton(j, 3) - 0.5),
                     uLens=(halton(j, 5), halton(j, 7)), uSeed=float(j))
            for k, v in u.items():
                self._set(p, k, v)
            for s in range(self.tiles):
                y0, y1 = self.H * s / self.tiles, self.H * (s + 1) / self.tiles
                self._set(p, 'uRegion', (0, y0, self.W, y1))
                self.ctx.scissor = (0, int(y0), self.W, int(np.ceil(y1 - y0)))
                vao.render(moderngl.TRIANGLES)
                if self.tiles > 1:
                    self.ctx.finish()
        self.ctx.scissor = None
        self.ctx.disable(moderngl.BLEND)
        self.hdr_fbo.use()
        self.acc.use(0)
        self.progs['_resolve']['uAcc'] = 0
        self.progs['_resolve']['uInv'] = 1.0 / spp
        self.vaos['_resolve'].render(moderngl.TRIANGLES)
        self.hdr.build_mipmaps()
        pp = dict(exposure=1.0, bloom=0.6, bloom_thr=1.0, sat=1.0, contrast=1.0, vignette=0.35, grain=0.03, flash=0.0,
                  fade=1.0, ca=0.0)
        pp.update(post or {})
        q = self.progs['_post']
        self.out_fbo.use()
        self.hdr.use(0)
        q['uHdr'] = 0
        for k, v in dict(uRes=(self.W, self.H), uExposure=pp['exposure'], uBloom=pp['bloom'], uBloomThr=pp['bloom_thr'],
                         uSat=pp['sat'], uContrast=pp['contrast'], uVignette=pp['vignette'], uGrain=pp['grain'],
                         uFlash=pp['flash'], uFade=pp['fade'], uCA=pp['ca'], uSeed=float(t * 37 % 100)).items():
            self._set(q, k, v)
        self.vaos['_post'].render(moderngl.TRIANGLES)
        return np.frombuffer(self.out_fbo.read(components=3), np.uint8).reshape(self.H, self.W, 3)[::-1].copy()
