"""Light and colour-vision maths for videos about optics, rainbows, spectra and animal / colour-blind vision.

Everything works on a wavelength grid LAM (nm, default 300..730 step 5) so UV-sensitive eyes (bees, birds, shrimp)
can be modelled too. No data files: the curves are analytic fits.

  wavelength_rgb(nm)            pretty sRGB rainbow colour (Bruton ramp, soft fall-off at both ends) - for drawing
  cmf()                         CIE 1931 2-deg colour matching functions (Wyman, Sloan & Shirley 2013 fit), (3, n)
  daylight()                    smooth ~6500 K illuminant (Planck, deep UV cut), peak 1
  spectrum_xyz(refl, light)     reflectance -> XYZ, white-normalised (perfect white under `light` -> Y = 1)
  xyz_to_linear(xyz)            -> linear sRGB;   linear_to_srgb / srgb_to_linear  (gamma, arrays or tuples)
  opsin(lmax)                   Govardovskii et al. 2000 A1 photopigment template (alpha + beta band), peak 1
  catches(refl, sens, light)    quantum catches of a set of receptors, von Kries-normalised (white -> 1 each)
  simulate_dichromat(rgb, kind) Vienot, Brettel & Mollon 1999 protan / deutan simulation on linear sRGB
  g / sig                       Gaussian bump / logistic step on LAM for building reflectance spectra

Example - what a bee sees of a yellow petal that reflects UV (standard false colour UV->blue, B->green, G->red):
    petal = 0.06 + 0.84 * sig(510, 11) + 0.55 * g(345, 22)
    uv, b, gr = catches(petal, [opsin(344), opsin(436), opsin(544)])
    rgb = linear_to_srgb([gr, b, uv])
"""
import math
import numpy as np

LAM = np.arange(300.0, 731.0, 5.0)


def g(mu, s, lam=None):
    lam = LAM if lam is None else lam
    return np.exp(-0.5 * ((lam - mu) / s) ** 2)


def sig(mu, w, lam=None):
    lam = LAM if lam is None else lam
    return 1 / (1 + np.exp(-(lam - mu) / w))


def _g2(lam, mu, s1, s2):
    s = np.where(lam < mu, s1, s2)
    return np.exp(-0.5 * ((lam - mu) / s) ** 2)


def cmf(lam=None):
    lam = LAM if lam is None else np.asarray(lam, float)
    x = 1.056 * _g2(lam, 599.8, 37.9, 31.0) + 0.362 * _g2(lam, 442.0, 16.0, 26.7) - 0.065 * _g2(lam, 501.1, 20.4, 26.2)
    y = 0.821 * _g2(lam, 568.8, 46.9, 40.5) + 0.286 * _g2(lam, 530.9, 16.3, 31.1)
    z = 1.217 * _g2(lam, 437.0, 11.8, 36.0) + 0.681 * _g2(lam, 459.0, 26.0, 13.8)
    return np.stack([x, y, z])


def daylight(T=6500.0, lam=None):
    lam = LAM if lam is None else lam
    lm = lam * 1e-9
    s = 1 / (lm ** 5 * (np.exp(1.4388e-2 / (lm * T)) - 1))
    s = s / s.max()
    return s * sig(312, 8, lam)


M_XYZ_RGB = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])


def spectrum_xyz(refl, light=None, lam=None):
    lam = LAM if lam is None else lam
    light = daylight(lam=lam) if light is None else light
    C = cmf(lam)
    return (C * refl * light).sum(1) / (C[1] * light).sum()


def xyz_to_linear(xyz):
    return np.clip(M_XYZ_RGB @ np.asarray(xyz, float), 0, None)


def linear_to_srgb(c):
    a = np.clip(np.asarray(c, float), 0, None)
    out = np.where(a <= 0.0031308, 12.92 * a, 1.055 * np.power(a, 1 / 2.4) - 0.055)
    return np.minimum(out, 1.0)


def srgb_to_linear(c):
    a = np.clip(np.asarray(c, float), 0, 1)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def opsin(lmax, lam=None):
    lam = LAM if lam is None else np.asarray(lam, float)
    x = lmax / lam
    a = 0.8795 + 0.0459 * math.exp(-(lmax - 300) ** 2 / 11940)
    al = 1 / (np.exp(69.7 * (a - x)) + np.exp(28 * (0.922 - x)) + np.exp(-14.9 * (1.104 - x)) + 0.674)
    lb, bb = 189 + 0.315 * lmax, -40.5 + 0.195 * lmax
    s = al + 0.26 * np.exp(-((lam - lb) / bb) ** 2)
    return s / s.max()


def catches(refl, sens, light=None, lam=None):
    lam = LAM if lam is None else lam
    light = daylight(lam=lam) if light is None else light
    return np.array([(s * refl * light).sum() / (s * light).sum() for s in sens])


_DICHRO = {
    'protan': np.array([[0.11238, 0.88762, 0.0], [0.11238, 0.88762, 0.0], [0.00401, -0.00401, 1.0]]),
    'deutan': np.array([[0.29275, 0.70725, 0.0], [0.29275, 0.70725, 0.0], [-0.02234, 0.02234, 1.0]]),
}


def simulate_dichromat(rgb_linear, kind='deutan'):
    """rgb_linear: (..., 3) linear sRGB -> what a protanope / deuteranope sees (linear sRGB)."""
    M = _DICHRO[kind]
    return np.clip(np.asarray(rgb_linear, float) @ M.T, 0, None)


def wavelength_rgb(nm, gain=1.0):
    """sRGB tuple for drawing a wavelength (380..730 nm visible; black outside). Not colorimetric: a smooth,
    saturated ramp that looks like a rainbow on screen (the CIE path clips to odd pinks at the red end)."""
    l = float(nm)
    if l < 440:
        c = (-(l - 440) / 60.0, 0.0, 1.0)
    elif l < 490:
        c = (0.0, (l - 440) / 50.0, 1.0)
    elif l < 510:
        c = (0.0, 1.0, -(l - 510) / 20.0)
    elif l < 580:
        c = ((l - 510) / 70.0, 1.0, 0.0)
    elif l < 645:
        c = (1.0, -(l - 645) / 65.0, 0.0)
    else:
        c = (1.0, 0.0, 0.0)
    if l < 420:
        f = 0.3 + 0.7 * (l - 380) / 40.0
    elif l > 680:
        f = 0.3 + 0.7 * (730 - l) / 50.0
    else:
        f = 1.0
    f = max(0.0, min(1.0, f)) if 380 <= l <= 730 else 0.0
    return tuple(min(1.0, (max(0.0, min(1.0, v)) * f * gain) ** 0.85) for v in c)
