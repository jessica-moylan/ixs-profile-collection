import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import bluesky.callbacks.fitting
import numpy as np
import pandas as pd
import lmfit
from bluesky.callbacks import LiveFit
from bluesky.suspenders import SuspendFloor
from ophyd import EpicsSignal
from tabulate import tabulate

# tm1sum = EpicsSignal('XF:10ID-BI:TM176:SumAll:MeanValue_RBV')
# susp = SuspendFloor(tm1sum, 1.e-5, resume_thresh = 1.e-5, sleep = 1*60)

# uofb_pv = EpicsSignal("SR:UOFB{}ConfigMode-I", name="uofb_pv")
# id_bump_pv = EpicsSignal("SR:UOFB{C10-ID}Enabled-I", name="id_bump_pv")
# nudge_pv = EpicsSignal("SR:UOFB{C10-ID}Nudge-Enabled", name="nudge_pv")

def align_with_fit(dets, mtr, start, stop, gaps, mode='rel', md=None):
    # Performs relative scan of motor and retuns data staistics

    md = md or {}
    plt.cla()

    local_peaks = []
    for det in dets:
        for hint in det.hints['fields']:
            local_peaks.append(
                bluesky.callbacks.fitting.PeakStats(mtr.hints['fields'][0], hint)
            ) 
    # TODO use relative wrapper to avoid the reset behavior (or make it optional)
    
    if mode == 'rel':
        plan = bpp.subs_wrapper(
            bp.rel_scan(dets, mtr, start, stop, gaps+1, md=md), 
            local_peaks
            )
    else:
        plan = bpp.subs_wrapper(
            bp.scan(dets, mtr, start, stop, gaps+1, md=md), 
            local_peaks
            )
    yield from plan
    return local_peaks


def check_zero(dets=[lambda_det], start=-20, stop=20, gaps=200, exp_time=1, md=None):
    # Performs relative scan of the HRM energy at tth = 0 and positions it to the peak center

    #
    print('scanning zero')
    #
    md = md or {}
    yield from bps.mv(spec.tth, 0)
    sample_pos = yield from bps.read(sample_stage)
    print(sample_pos)
#    if dets is None:
#        dets = [lambda_det]

    yield from set_lambda_exposure(exp_time)
    yield from bps.mv(whl, 7)
    for d in dets:
        # set the exposure times
        pass

    local_peaks = yield from align_with_fit(dets, hrmE, start, stop, gaps, 'rel', md)
    cen = local_peaks[0].cen

    peak_stats = bec.peaks
    peaks_stats_print('lambda_det_stats7_total', peak_stats)

    if cen is not None:
        target = 0.2 * round(cen/0.2)
        # move too far for backlash compensation
        yield from bps.mv(hrmE, target - 20)
        # apporach target from negative side 
        yield from bps.mv(hrmE, target)
        print('\n')
        print(f"HRM energy is set to E = {hrmE.energy.read()['hrmE']['value']}\n")

def do_the_right_thing(i_time):
    yield from bps.mv(det1.integration_time, i_time)
    yield from count([det1])

def ct(exp_time):
    yield from bps.mv(sclr.preset_time, exp_time)
    yield from bp.count([sclr])


def double_ct(exp_time):
    yield from ct(exp_time)
    # yield from bps.mv(sample_stage.sx, 0)
    yield from ct(exp_time)

def Lipid_Qscan(Qq=None, Ncycles=1, md=None):
    # Test plan for the energy scan at several Q values
    # Usage: 
    md = md or {}
    tth001 = 16.8
#    Qq = [1, 2, 3]
    c22 = sclr.channels.chan22
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    yield from bps.mv(mcm_slits.inboard, -1, mcm_slits.outboard, 1)

    for kk in range(Ncycles):
        yield from bps.mv(anapd, 25)
        #yield from set_lambda_exposure(2)
        yield from check_zero(start=-5, stop=5, gaps=40, exp_time=1)
        yield from bps.mv(whl, 0)
        if Qq == None:
            print('\n')
            print('Empty Q-list. Scan is finished.\n')
            return
        else:
            for q in Qq:
                print(f"Starting energy scan at Q = {q} nm-1\n")
                plt.cla()
                th = qq2th(q)
                yield from bps.mv(spec.tth, th)
                yield from hrmE_dscan(-5, 5, 10, 2, md=md)

#                yield from bps.mvr(sample_stage.sx, 0.03)
                print(f"Moving the TTH to the Tth = {tth001} angle\n")
                yield from bps.mv(spec.tth, tth001)
                yield from set_lambda_exposure(5)

                print("Scanning the sample SSY\n")
                yield from bp.rel_scan([lambda_det], sample_stage.sy, -0.1, 0.1, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mvr(sample_stage.sy, -0.1)
                yield from bps.mv(sample_stage.sy, max_pos)
                print(f"Sample stage SY is set to {sample_stage.sy.read()['s_sy']['value']}\n")

                print("Scanning the sample SSZ\n")
                yield from bp.scan([lambda_det], sample_stage.sz, -2, 2, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mv(sample_stage.sz, max_pos)
                print(f"Sample stage SZ is set to {sample_stage.sz.read()['s_sz']['value']}\n")

                print("Scanning the sample SSY\n")
                yield from bp.rel_scan([lambda_det], sample_stage.sy, -0.1, 0.1, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mvr(sample_stage.sy, -0.1)
                yield from bps.mv(sample_stage.sy, max_pos)
                print(f"Sample stage SY is set to {sample_stage.sy.read()['s_sy']['value']}\n")


def Dia_scan(exp_time=60):
    # Test plan for Diamond
    # yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    # yield from bps.mv(anapd, 25, whl, 0)

    myaxs.cla()
    # yield from set_lambda_exposure(exp_time)
    yield from dscan(hrmE, -14, 14, 56, lambda_det, exp_time)

from bluesky import plan_stubs as bps
from bluesky import plans as bp


def Dia_energy_scan_plan():
    E0 = 23.66

    for kk in range(10):
        # Initial setup
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)
        yield from bps.mv(whl, 5)
        # chk_thresh = 0
        res = yield from dscan(hrmE, 0, 20, 100, lambda_det, 2)
        # breakpoint()
        cen = res[0]['stats'][3]

        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        # Positive q offsets
        for scale, rng, steps in [(1.01, 10, 40), (1.02, 14, 56), (1.03, 18, 72), (1.04, 22, 88), (1.05, 26, 104)]:
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 60
            # yield from set_lambda_exposure(ctime)
            ca(scale, scale, scale)
            yield from br(scale, scale, scale)
            res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # Recalibrate energy zero
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)

        yield from bps.mv(whl, 5)
        # chk_thresh = 0
        res = yield from dscan(hrmE, 0, 20, 100, lambda_det, 2)
        cen = res[0]['stats'][3]

        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        # Negative q offsets
        for scale, rng, steps in [(0.99, 10, 40), (0.98, 14, 56), (0.97, 18, 72), (0.96, 22, 88), (0.95, 26, 104)]:
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 60
            # yield from set_lambda_exposure(ctime)
            ca(scale, scale, scale)
            yield from br(scale, scale, scale)
            res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)


def Dia_TA_scan_plan():
    # plan for energy spectra in diamond from transverse acoustic waves
    E0 = 49.6

    for kk in range(10):
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        # Move to initial energy
        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)
        yield from bps.mv(whl, 5)

        # First dscan
        rng, steps = 20, 100
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, 2)
        cen = res[0]['stats'][3]  # replaced CEN with parsed result
        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        hh = 0.01

        # 1st detailed scan set
        yield from bps.mv(whl, 0)
        ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 - 2*hh, 1 + 2*hh, 1)
        yield from br(1 - 2*hh, 1 + 2*hh, 1)
        rng, steps = 10, 40
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 2nd detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 - 3*hh, 1 + 3*hh, 1)
        yield from br(1 - 3*hh, 1 + 3*hh, 1)
        rng, steps = 15, 60
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 3rd detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 - 4*hh, 1 + 4*hh, 1)
        yield from br(1 - 4*hh, 1 + 4*hh, 1)
        rng, steps = 20, 80
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 4th detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 - 5*hh, 1 + 5*hh, 1)
        yield from br(1 - 5*hh, 1 + 5*hh, 1)
        rng, steps = 25, 100
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)


def Dia_energy_scan_plan_20251110():
    E0 = 23.66

    for kk in range(1):
        # Initial setup
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)

        yield from bps.mv(whl, 5)
        # chk_thresh = 0
        res = yield from dscan(hrmE, 0, 20, 100, lambda_det, 2)
        # breakpoint()
        cen = res[0]['stats'][3]

        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        # Positive q offsets
        for scale, rng, steps in [(1.01, 10, 40), (1.02, 14, 56), (1.03, 18, 72), (1.04, 22, 88), (1.05, 26, 104)]:
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 60
            # yield from set_lambda_exposure(ctime)
            ca(scale, scale, scale)
            yield from br(scale, scale, scale)
            res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # Recalibrate energy zero
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)

        yield from bps.mv(whl, 5)
        # chk_thresh = 0
        res = yield from dscan(hrmE, 0, 20, 100, lambda_det, 2)
        cen = res[0]['stats'][3]

        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        # Negative q offsets
        for scale, rng, steps in [(0.99, 10, 40), (0.98, 14, 56), (0.97, 18, 72), (0.96, 22, 88), (0.95, 26, 104)]:
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 60
            # yield from set_lambda_exposure(ctime)
            ca(scale, scale, scale)
            yield from br(scale, scale, scale)
            res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)


    for kk in range(1):
        ca(1, 1, 1)
        yield from br(1, 1, 1)
        wh()

        # Move to initial energy
        yield from bps.mv(hrmE, E0 - 10)
        # yield from set_lambda_exposure(2)
        yield from bps.mv(whl, 5)

        # First dscan
        rng, steps = 20, 100
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, 2)
        cen = res[0]['stats'][3]  # replaced CEN with parsed result
        pos = 0.2 * round(cen / 0.2)
        print(f"new energy zero = {pos}")
        yield from bps.mv(hrmE, pos)
        E0 = pos

        hh = 0.01

        # 1st detailed scan set
        yield from bps.mv(whl, 0)
        ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 + hh, 1 + hh, 1 - 2*hh)
        yield from br(1 + hh, 1 + hh, 1 - 2*hh)
        rng, steps = 5, 20
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 2nd detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 + 2*hh, 1 + 2*hh, 1 - 4*hh)
        yield from br(1 + 2*hh, 1 + 2*hh, 1 - 4*hh)
        rng, steps = 10, 40
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 3rd detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 + 3*hh, 1 + 3*hh, 1 - 6*hh)
        yield from br(1 + 3*hh, 1 + 3*hh, 1 - 6*hh)
        rng, steps = 15, 60
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

        # 4th detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 + 4*hh, 1 + 4*hh, 1 - 8*hh)
        yield from br(1 + 4*hh, 1 + 4*hh, 1 - 8*hh)
        rng, steps = 20, 80
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)

          # 5th detailed scan set
        # ctime = 60
        # yield from set_lambda_exposure(ctime)
        ca(1 + 5*hh, 1 + 5*hh, 1 - 10*hh)
        yield from br(1 + 5*hh, 1 + 5*hh, 1 - 10*hh)
        rng, steps = 25, 100
        res = yield from dscan(hrmE, -rng, rng, steps, lambda_det, ctime)



def Te_surph_energy_scan_plan_20251202():
    E0 = -17.283

    for kk in range(3):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.1, 0, 22, 89), (0.5, 0, 22, 89)]:
            # Initial setup
            ca(1, 0, 4)
            yield from br(1, 0, 4)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 180
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)

       
def Te_surph_energy_scan_plan_20251204():
    E0 = -17.3

    for kk in range(4):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.9, 10, 20, 41), (0.5, 9, 21, 49), (0.1, 10, 20, 41)]:
            # Initial setup
            ca(1, 0, 4)
            yield from br(1, 0, 4)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 240
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)


def Te_surph_energy_scan_plan_20251205():
    E0 = -17.3

    for kk in range(4):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.9, 10, 20, 41)]:
            # Initial setup
            ca(1, 0, 4)
            yield from br(1, 0, 4)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 240
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)


def Te_surph_energy_scan_plan_20251206():
    E0 = -17.4

    for kk in range(3):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.9, 0, 9.75, 40),(0.9, 10, 22, 49)]:
            # Initial setup
            ca(1, 0, 4)
            yield from br(1, 0, 4)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 240
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)



def Te_surph_energy_scan_plan_20251207():
    E0 = -17.52

    for kk in range(3):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.9, 10, 22, 49)]:
            # Initial setup
            ca(1, 0, 3)
            yield from br(1, 0, 3)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 240
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)


def Te_surph_energy_scan_plan_20251208():
    E0 = -17.59

    for kk in range(6):

    # Positive q offsets
        for scale, rng1, rng2, steps in [(0.9, 10, 20, 41)]:
            # Initial setup
            ca(1, 0, 3)
            yield from br(1, 0, 3)
            wh()

            yield from bps.mv(hrmE, E0 - 10)
            # yield from set_lambda_exposure(2)

            yield from bps.mv(whl, 3)
            # chk_thresh = 0
            res = yield from dscan(hrmE, 0, 20, 101, lambda_det, 2)
            # breakpoint()
            cen = res[0]['stats'][3]

            pos = 0.2 * round(cen / 0.2)
            print(f"new energy zero = {pos}")
            yield from bps.mv(hrmE, pos)
            E0 = pos
            
            
            yield from bps.mv(whl, 0)
            # chk_thresh = 30
            ctime = 240
            # yield from set_lambda_exposure(ctime)
            ca(1, 0, 4-scale)
            yield from br(1, 0, 4-scale)
            yield from dscan(hrmE, rng1, rng2, steps, lambda_det, ctime)
            

def test_plan():
    # yield from set_lambda_exposure(2)
    # res = yield from dscan(hrmE, -10, 10, 5, lambda_det, md={'count_time': 2})
    # yield from bps.mv(analyzer_slits.top, 0.)
    res = yield from dscan(analyzer_slits.top, -0.1, 0.1, 3, det2, 1, det_ch=[0])
    # yield from bps.mv(analyzer_slits.top, 1.)
    print(res)
    print("**********************************************************************")
    print(f"cen  = {res[0].cen}")
    print(f"fwhm = {res[0].fwhm}")
    print(f"com  = {res[0].com}")
    print(f"vmax = {res[0].max}")
    print(f"vmin = {res[0].min}")
    print(f"crxs = {res[0].crossings} ")
    print("**********************************************************************")