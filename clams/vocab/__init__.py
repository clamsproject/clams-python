# TODO (krim @ 10/7/2018): reimplement with proper enum
class AnnotationTypes(object):
    FA = "vanilla-forced-alignment"
    FFA = "filtered-forced-alignment"
    BD = "bar-detection"
    TD = "tone-detection"
    ND = "noise-detection"


class MediaTypes(object):
    V = "audio-video"
    A = "audio-only"
    T = "text"
