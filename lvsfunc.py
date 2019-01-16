import vapoursynth as vs
import vsTAAmbk as taa  # https://github.com/HomeOfVapourSynthEvolution/vsTAAmbk
import fvsfunc as fvf  # https://github.com/Irrational-Encoding-Wizardry/fvsfunc
import mvsfunc as mvf  # https://github.com/HomeOfVapourSynthEvolution/mvsfunc
import havsfunc as haf  # https://github.com/HomeOfVapourSynthEvolution/havsfunc
from nnedi3_rpow2 import nnedi3_rpow2 # https://github.com/darealshinji/vapoursynth-plugins/blob/master/scripts/nnedi3_rpow2.py

core = vs.core

# TO-DO: Write function that only masks px of a certain color/threshold of colors
# TO-DO: Rewrite 'compare'. Should be able to handle it in a much better way than how XEL did it.


def fix_eedi3(clip: vs.VideoNode, strength=1, alpha=0.25, beta=0.5, gamma=40, nrad=2, mdis=20, nsize=3, nns=3, qual=1):
    """
    Script written by Zastin. What it does is clamp the "change" done by eedi3 to the "change" of nnedi3. This should
    fix every issue created by eedi3. For example: https://i.imgur.com/hYVhetS.jpg
    """

    if clip.format.bits_per_sample != 16:
        clip = fvf.Depth(clip, 16)
    bits = clip.format.bits_per_sample - 8
    thr = strength * (1 >> bits)
    strong = taa.TAAmbk(clip, aatype='Eedi3', alpha=alpha, beta=beta, gamma=gamma, nrad=nrad, mdis=mdis, mtype=0)
    weak = taa.TAAmbk(clip, aatype='Nnedi3', nsize=nsize, nns=nns, qual=qual, mtype=0)
    expr = 'x z - y z - * 0 < y x y {l} + min y {l} - max ?'.format(l=thr)
    if clip.format.num_planes > 1:
        expr = [expr, '']
    aa = core.std.Expr([strong, weak, clip], expr)
    mask = clip.std.Prewitt(planes=0).std.Binarize(50 >> bits, planes=0).std.Maximum(planes=0).std.Convolution([1] * 9,
                                                                                                               planes=0)
    return clip.std.MaskedMerge(aa, mask, planes=0)


def compare(clips: vs.VideoNode, frames, match_clips=True):
    """
    Script written XEL8o9 and slightly modified by me. Grabs a given frame from two clips for easier comparison.
    Intended order is [src, filtered].
    
    Example use:
    lvf.compare([src, filtered], [10, 20, 30, 40, 50], match_clips=True)
    """
    if len(clips) < 2:
        raise ValueError('compare: There must be at least two clips')
    width = clips[0].width
    height = clips[0].height
    for i in range(0, len(clips)):
        if clips[i].format.bits_per_sample != 16:
            clips[i] = fvf.Depth(clips[i], 16)
    final = None
    for frame in frames:
        newClip = core.std.Trim(clips[0], frame, frame)
        for i in range(1, len(clips)):
            nextFrame = core.std.Trim(clips[i], frame, frame)
            if nextFrame.width != width or nextFrame.height != height:
                if match_clips:
                    nextFrame = core.resize.Spline36(nextFrame, width, height)
                else:
                    raise ValueError('compare: The dimensions of each clip must be equal')
            newClip += nextFrame
        if final is None:
            final = newClip
        else:
            final += newClip
    return final


def stack_compare(clip_a: vs.VideoNode, clip_b: vs.VideoNode, width=None, height=None, stack_vertical=False):
    """
    Compares two frames by stacking.
    Best to use when trying to match two sources frame-accurately, however by setting height to the source's height (or None) it can be used for comparisons that way.
    """
    if clip_a.format.bits_per_sample != clip_b.format.bits_per_sample:
        raise ValueError('stack_compare: The bitdepth of both clips must be equal')
    if clip_a.format.id != clip_b.format.id:
        raise ValueError('stack:compare: The subsampling of both clips must be equal')

    if height is None:
        height = clip_a.height
    if width is None:
        width = getw(height, ar=clip_a.width / clip_a.height)

    clip_a = core.resize.Spline36(clip_a, width, height)
    clip_b = core.resize.Spline36(clip_b, width, height)

    if stack_vertical:
        stacked = core.std.StackVertical([clip_a, clip_b])
    else:
        stacked = core.std.StackHorizontal([clip_a, clip_b])

    return stacked



def super_aa(clip: vs.VideoNode, width=None, Height=None, mode=1):
    """
    Script written by Zastin and modified by me. Useful for shows like Yuru Camp with bad lineart problems.
    
    Mode 1 = Nnedi3 
    Mode 2 = Eedi3
    """
    if clip.format.bits_per_sample != 16:
        clip = fvf.Depth(clip, 16)
    srcY = clip.std.ShufflePlanes(0, vs.GRAY)

    if height is None:
        height = srcY.height
    if width is None:
        width = getw(height, ar=srcY.width / srcY.height)

    if mode is 1:
        def aa(srcY):
            srcY = srcY.std.Transpose()
            srcY = srcY.nnedi3.nnedi3(0, 1, 0, 3, 3, 2)
            srcY = srcY.nnedi3.nnedi3(1, 0, 0, 3, 3, 2)
            srcY = srcY.resize.Spline36(height, width, src_top=.5)
            srcY = srcY.std.Transpose()
            srcY = srcY.nnedi3.nnedi3(0, 1, 0, 3, 3, 2)
            srcY = srcY.nnedi3.nnedi3(1, 0, 0, 3, 3, 2)
            srcY = srcY.resize.Spline36(width, height, src_top=.5)
            return srcY
    elif mode is 2:
        def aa(srcY):
            w, h = srcY.width, srcY.height
            srcY = srcY.std.Transpose()
            srcY = srcY.eedi3m.EEDI3(0, 1, 0, 0.5, 0.2)
            srcY = srcY.znedi3.nnedi3(1, 0, 0, 3, 4, 2)
            srcY = srcY.resize.Spline36(height, width, src_top=.5)
            srcY = srcY.std.Transpose()
            srcY = srcY.eedi3m.EEDI3(0, 1, 0, 0.5, 0.2)
            srcY = srcY.znedi3.nnedi3(1, 0, 0, 3, 4, 2)
            srcY = srcY.resize.Spline36(width, height, src_top=.5)
            return srcY
    else:
        raise ValueError('super_aa: unknown mode')

    def csharp(flt, src):
        blur = core.std.Convolution(flt, [1] * 9)
        return core.std.Expr([flt, src, blur], 'x y < x x + z - x max y min x x + z - x min y max ?')

    aaclip = aa(srcY)
    aaclip = csharp(aaclip, srcY).rgvs.Repair(srcY, 13)

    if clip.format.color_family is vs.GRAY:
        return aaclip
    else:
        srcU = clip.std.ShufflePlanes(1, vs.GRAY)
        srcV = clip.std.ShufflePlanes(2, vs.GRAY)
        merged = core.std.ShufflePlanes([aaclip, srcU, srcV], 0, vs.YUV)
        return merged

def getw(h, ar=16 / 9, only_even=True):
    """
    returns width for image (taken from kagefunc)
    """
    w = h * ar
    w = int(round(w))
    if only_even:
        w = w // 2 * 2
    return w

def denoise(clip: vs.VideoNode, mode=1, bm3d=True, sigma=3, h=1.0, refine_motion=True, sbsize=16):
    """
    Generic denoising. Denoising is done by BM3D with other denoisers being used for ref. Returns the denoised clip used
    as ref if BM3D=False.

    Mode 1 = KNLMeansCL
    Mode 2 = SMDegrain
    Mode 3 = DFTTest
    """
    if clip.format.bits_per_sample != 16:
        clip = fvf.Depth(clip, 16)
    clipY = core.std.ShufflePlanes(clip, 0, vs.GRAY)

    if mode == 1 or knlm:
        denoiseY = clipY.knlm.KNLMeansCL(d=3, a=2, h=h)
    elif mode == 2 or SMD:
        denoiseY = haf.SMDegrain(clipY, prefilter=3, RefineMotion=refine_motion)
    elif mode == 3 or DFT:
        denoiseY = clipY.dfttest.DFTTest(sigma=4.0, tbsize=1, sbsize=sbsize, sosize=sbsize*0.75)
    else:
        raise ValueError('denoise: unknown mode')

    if bm3d:
        denoisedY = mvf.BM3D(clipY, sigma=sigma, psample=0, radius1=1, ref=denoiseY)

    if bm3d is False:
        denoisedY = denoiseY

    if clip.format.color_family is vs.GRAY:
        return denoisedY
    else:
        srcU = clip.std.ShufflePlanes(1, vs.GRAY)
        srcV = clip.std.ShufflePlanes(2, vs.GRAY)
        merged = core.std.ShufflePlanes([denoisedY, srcU, srcV], 0, vs.YUV)
        return merged


def Source(path_to_clip, mode='lsmas', resample=False):
    """
    Just a stupid import script. There really is no reason to use this, but hey, it was fun to write.
    """

    if path_to_clip.startswith("file:///"):
        path_to_clip = path_to_clip[8::]

    if path_to_clip.endswith(".d2v"):
        src = core.d2v.Source(path_to_clip)
    else:
        if mode == 1 or 'lsmas':
            src = core.lsmas.LWLibavSource(path_to_clip)
        elif mode == 2 or 'ffms2':
            src = core.ffms2.Source(path_to_clip)
        else:
            raise ValueError('source: Unknown mode')
      
    if resample:
        src = fvf.Depth(src, 16)

    return src

# Source alias (for additional autism)
src = Source