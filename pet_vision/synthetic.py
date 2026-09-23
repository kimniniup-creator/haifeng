"""Generated landmarks for logic tests; never a claim of camera recognition."""
from .core import Hand, Observation


def open_hand(x=0., confidence=.9, handedness="Left"):
    points = [(0.5 + x, .8, 0.)] * 21
    points[1:5] = [(.44+x,.7,0.),(.38+x,.6,0.),(.32+x,.5,0.),(.26+x,.4,0.)]
    for base, px in ((5,.42),(9,.48),(13,.54),(17,.60)):
        for offset, py in enumerate((.6,.48,.36,.25)):
            points[base+offset] = (px+x,py,0.)
    return Hand(tuple(points), confidence, handedness)


def demo_observations(start):
    for i in range(8):
        yield Observation(start+i*.1, (open_hand(),))
    for i in range(8,16):
        yield Observation(start+i*.1)
    xs = [0,.06,.12,.06,0,-.06,0,.06,.12]
    for i,x in enumerate(xs,16):
        yield Observation(start+i*.1, (open_hand(x, handedness="Left" if i%2 else "Right"),))
