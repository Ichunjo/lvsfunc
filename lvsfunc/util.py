"""
    Helper functions for the main functions in the script.
"""
from functools import partial
from typing import Any, Callable, List, Optional, Sequence, Type, TypeVar, Tuple, Union

import vapoursynth as vs
from vsutil import depth

from .types import Range

core = vs.core


def quick_resample(clip: vs.VideoNode,
                   function: Callable[[vs.VideoNode], vs.VideoNode]
                   ) -> vs.VideoNode:
    """
    A function to quickly resample to 16/8 bit and back to the original depth.
    Useful for filters that only work in 16 bit or lower when you're working in float.

    :param clip:      Input clip
    :param function:  Filter to run after resampling (accepts and returns clip)

    :return:          Filtered clip in original depth
    """
    if clip.format is None:
        raise ValueError("quick_resample: 'Variable-format clips not supported'")
    try:
        down = depth(clip, 16)
        filtered = function(down)
    except:  # noqa: E722
        down = depth(clip, 8)
        filtered = function(down)
    return depth(filtered, clip.format.bits_per_sample)


def pick_repair(clip: vs.VideoNode) -> Callable[..., vs.VideoNode]:
    """
    Returns rgvs.Repair if the clip is 16 bit or lower, else rgsf.Repair.
    This is done because rgvs doesn't work with float, but rgsf does for whatever reason.

    Dependencies: rgsf

    :param clip: Input clip

    :return:     Appropriate repair function for input clip's depth
    """
    if clip.format is None:
        raise ValueError("pick_repair: 'Variable-format clips not supported'")
    return core.rgvs.Repair if clip.format.bits_per_sample < 32 else core.rgsf.Repair


def pick_removegrain(clip: vs.VideoNode) -> Callable[..., vs.VideoNode]:
    """
    Returns rgvs.RemoveGrain if the clip is 16 bit or lower, else rgsf.RemoveGrain.
    This is done because rgvs doesn't work with float, but rgsf does for whatever reason.

    Dependencies:

    * RGSF

    :param clip: Input clip

    :return:     Appropriate RemoveGrain function for input clip's depth
    """
    if clip.format is None:
        raise ValueError("pick_removegrain: 'Variable-format clips not supported'")
    return core.rgvs.RemoveGrain if clip.format.bits_per_sample < 32 else core.rgsf.RemoveGrain


VideoProp = Union[
    int, Sequence[int],
    float, Sequence[float],
    str, Sequence[str],
    vs.VideoNode, Sequence[vs.VideoNode],
    vs.VideoFrame, Sequence[vs.VideoFrame],
    Callable[..., Any], Sequence[Callable[..., Any]]
]

T = TypeVar("T", bound=VideoProp)


def get_prop(frame: vs.VideoFrame, key: str, t: Type[T]) -> T:
    """
    Gets FrameProp ``prop`` from frame ``frame`` with expected type ``t``
    to satisfy the type checker.

    :param frame:   Frame containing props
    :param key:     Prop to get
    :param t:       Type of prop

    :return:        frame.prop[key]
    """
    try:
        prop = frame.props[key]
    except KeyError:
        raise KeyError(f"get_prop: 'Key {key} not present in props'")

    if not isinstance(prop, t):
        raise ValueError(f"get_prop: 'Key {key} did not contain expected type: Expected {t} got {type(prop)}'")

    return prop


def select_frames(clips: Union[vs.VideoNode, List[vs.VideoNode]],
                  indicies: Sequence[Union[int, Tuple[int, int]]]) -> vs.VideoNode:
    """
    Select frames from one or more clips at specified indices.

    :param clips:   A clip or a list of clips to select the frames from
    :param indexes: Indices of frames to select.

                    Provide a list of indices for a single clip, or for multiple clips, a list of tuples in the
                    form ``(clip_index, frame_index)``

    :return:        The selected frames in a single clip
    """
    clips = [clips] if isinstance(clips, vs.VideoNode) else clips
    indicies = list(indicies)

    for pos, index in enumerate(indicies):
        if isinstance(index, int):
            new_index = (0, index)
            indicies[pos] = new_index
        else:
            new_index = index
        clip_idx, frame_idx = new_index
        if not 0 <= clip_idx <= len(clips):
            raise IndexError(f"Clip index {clip_idx} out of range")
        if not 0 <= frame_idx <= clips[clip_idx].num_frames:
            raise IndexError(f"Frame index {frame_idx} out of range for clip {clip_idx}")

    if clips[0].format is None:
        raise ValueError("Only constant format clips are supported.")
    if len(clips) > 1 and not all(clip.format == clips[0].format for clip in clips[1:]):
        raise ValueError("All input clips must be of the same format.")

    def _select_frames_func(n: int, clips: List[vs.VideoNode], indicies: List[Tuple[int, int]]) -> vs.VideoNode:
        return clips[indicies[n][0]][indicies[n][1]]  # fuck me this is ugly

    length = len(indicies)
    placeholder_clip = clips[0]
    if length != placeholder_clip.num_frames:
        placeholder_clip = core.std.BlankClip(placeholder_clip, length=length)

    return core.std.FrameEval(placeholder_clip, partial(_select_frames_func, clips=clips, indicies=indicies))


def normalize_ranges(clip: vs.VideoNode, ranges: Union[Range, List[Range]]) -> List[Tuple[int, int]]:
    """
    Normalize ``Range``\\(s) to a list of inclusive positive integer ranges.

    :param clip:   Reference clip used for length.
    :param ranges: Single ``Range`` or list of ``Range``\\s.

    :return:       List of inclusive positive ranges.
    """
    ranges = ranges if isinstance(ranges, list) else [ranges]

    out = []
    for r in ranges:
        if isinstance(r, tuple):
            start, end = r
            if start is None:
                start = 0
            if end is None:
                end = clip.num_frames - 1
        elif r is None:
            start = clip.num_frames - 1
            end = clip.num_frames - 1
        else:
            start = r
            end = r
        if start < 0:
            start = clip.num_frames - 1 + start
        if end < 0:
            end = clip.num_frames - 1 + end
        out.append((start, end))

    return out


def replace_ranges(clip_a: vs.VideoNode,
                   clip_b: vs.VideoNode,
                   ranges: Union[Range, List[Range], None]) -> vs.VideoNode:
    """
    A replacement for ReplaceFramesSimple that uses ints and tuples rather than a string.
    Frame ranges are inclusive.

    Examples with clips ``black`` and ``white`` of equal length:

        * ``replace_ranges(black, white, [(0, 1)])``: replace frames 0 and 1 with ``white``
        * ``replace_ranges(black, white, [(None, None)])``: replace the entire clip with ``white``
        * ``replace_ranges(black, white, [(0, None)])``: same as previous
        * ``replace_ranges(black, white, [(200, None)])``: replace 200 until the end with ``white``
        * ``replace_ranges(black, white, [(200, -1)])``: replace 200 until the end with ``white``,
          leaving 1 frame of ``black``

    :param clip_a:     Original clip
    :param clip_b:     Replacement clip
    :param ranges:     Ranges to replace clip_a (original clip) with clip_b (replacement clip).

                       Integer values in the list indicate single frames,

                       Tuple values indicate inclusive ranges.

                       Negative integer values will be wrapped around based on clip_b's length.

                       None values are context dependent:

                           * None provided as sole value to ranges: no-op
                           * Single None value in list: Last frame in clip_b
                           * None as first value of tuple: 0
                           * None as second value of tuple: Last frame in clip_b

    :return:           Clip with ranges from clip_a replaced with clip_b
    """
    if ranges is None:
        return clip_a

    out_indicies = list(zip([0] * clip_a.num_frames, range(clip_a.num_frames)))
    clip_b_indices = list(zip([1] * clip_b.num_frames, range(clip_b.num_frames)))

    nranges = normalize_ranges(clip_b, ranges)

    for start, end in nranges:
        tmp = clip_b_indices[start:end + 1]
        if start != 0:
            tmp = out_indicies[: start] + tmp
        if end < len(out_indicies) - 1:
            tmp = tmp + out_indicies[end + 1:]
        out_indicies = tmp

    return select_frames([clip_a, clip_b], out_indicies)


def scale_thresh(thresh: float, clip: vs.VideoNode, assume: Optional[int] = None) -> float:
    """
    Scale binarization thresholds from float to int.

    :param thresh: Threshold [0, 1]. If greater than 1, assumed to be in native clip range
    :param clip:   Clip to scale to
    :param assume: Assume input is this depth when given input >1. If ``None``\\, assume ``clip``\\'s format.
                   (Default: None)

    :return:       Threshold scaled to [0, 2^clip.depth - 1] (if vs.INTEGER)
    """
    if clip.format is None:
        raise ValueError("scale_thresh: 'Variable-format clips not supported.'")
    if thresh < 0:
        raise ValueError("scale_thresh: 'Thresholds must be positive.'")
    if thresh > 1:
        return thresh if not assume \
            else round(thresh/((1 << assume) - 1) * ((1 << clip.format.bits_per_sample) - 1))
    return thresh if clip.format.sample_type == vs.FLOAT or thresh > 1 \
        else round(thresh * ((1 << clip.format.bits_per_sample) - 1))
