import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import bluesky.callbacks.fitting
import numpy as np
import pandas as pd
import lmfit
from bluesky.callbacks import LiveFit
from bluesky.callbacks.mpl_plotting import LiveGrid
from bluesky.suspenders import SuspendFloor
from ophyd import EpicsSignal
from tabulate import tabulate
import re

#from utils.sixcircle_1p53.sixcircle import *

#*******************************************************************************************************
# opens a Matplotlib figure with axes
# plt.ion()  # enable interactive mode
myfig, myaxs = plt.subplots(figsize=(8,5), num="Live Scan", clear=False)
myfig.canvas.manager.set_window_title("Live Scan")
myfig.show()
myfig.canvas.draw_idle()
myfig.canvas.flush_events()

#*******************************************************************************************************
def short_label(field):
    """
    Convert long ophyd/bluesky field names into short legend mnemonics.

    Examples
    --------
    det2_current2_mean_value -> det2.2
    det3_current7_mean_value -> det3.7
    lambda_det_stats7_total  -> lambda.7
    lambda_det_stats3_total  -> lambda.3
    tm1_sum_all_mean_value    -> tm1.4   # special case
    tm2_sum_all_mean_value    -> tm2.4   # special case
    """
    if field in ("tm1_sum_all_mean_value", "tm2_sum_all_mean_value"):
        name = field.split("_", 1)[0]
        return f"{name}.4"
    
    # Generic current-channel detector pattern
    m = re.fullmatch(r"(det\d+)_current(\d+)_mean_value", field)
    if m:
        det, ch = m.groups()
        return f"{det}.{ch}"

    # tm1 / tm2 pattern
    m = re.fullmatch(r"(tm\d+)_current(\d+)_mean_value", field)
    if m:
        det_name, ch = m.groups()
        return f"{det_name}.{ch}"

    # Lambda stats pattern
    m = re.fullmatch(r"lambda_det_stats(\d+)_total", field)
    if m:
        ch = m.group(1)
        return f"lambda.{ch}"

    # Fallback: return original field name unchanged
    return field

#*******************************************************************************************************
def peaks_stats_print(dets_name, peak_stats):

#    headers = ["com","cen","fwhm","max","min"]
    print(dets_name)
#    print(peak_stats)
    COM = peak_stats['stats'].com
    if COM == None:
        print(f"COM: None")
    else:
        print(f"COM: {COM:.3f}")

    CEN = peak_stats['stats'].cen
    if CEN == None:
        print(f"CEN: None")
    else:
        print(f"CEN: {CEN:.3f}")

    FWHM = peak_stats['stats'].fwhm
    if FWHM == None:
        print(f"FWHM: None")
    else:
        print(f"FWHM: {FWHM:.3f}")
    pmax = peak_stats['stats'].max[1]
    if pmax < 1 or pmax > 1.e4:
        print(f"MAX: {pmax:.1e} at {peak_stats['stats'].max[0]:.3f}")
    else:
        print(f"MAX: {pmax:.1f} at {peak_stats['stats'].max[0]:.3f}")
    pmin = peak_stats['stats'].min[1]
    if pmin < 1 or pmin > 1.e4:
        print(f"MIN: {pmin:.1e} at {peak_stats['stats'].min[0]:.3f}")
    else:
        print(f"MIN: {pmin:.1f} at {peak_stats['stats'].min[0]:.3f}")

#    data[2] = peak_stats[headers[2]][dets_name][1]
#    data[3] = peak_stats[headers[3]][dets_name][1]
#    print('\n')
#    print('*******************************************************')
#    print(tabulate([data], headers))
#    print('*******************************************************\n')


#*******************************************************************************************************
# def plotselect(det_name, mot_name):
# # creates a LivePlot object with given paramaters
#     # print(mot_name)
#     myplt = LivePlot(det_name, x=mot_name, marker='o', markersize=6, ax=myaxs, stream_name="primary")
#     return myplt

#*******************************************************************************************************
# def dscan(mot, start, stop, steps, det, ct, det_ch=None, md=None):
# # performs relative scan of a detector DET channel 
#     myaxs.cla()
#     myfig.canvas.draw_idle()

#     if det_ch is None:
#         det_ch = [0]
#     md = md or {}

#     md["count_time"] = ct
#     dets = [det, det134, sclr.channels.chan13, sr_curr]
#     # dets = [det]

#     # apply exposure if detector is lambda_det
#     if getattr(det, "name", None) == "lambda_det":
#         yield from set_lambda_exposure(ct)


#     subs_list = [plotselect(det.hints['fields'][det_channel], mot.name) for det_channel in  det_ch]
#     stats_list = [PeakStats(mot.name, det.hints['fields'][det_channel]) for det_channel in det_ch]

#     subs_list.extend(stats_list)
#     plan = bpp.subs_wrapper(bp.rel_scan(dets, mot, start, stop, steps, md=md), subs_list)
        
#     yield from plan

#     print('\n')
#     for n in range(len(det_ch)):
#         peaks_stats_print(det.hints['fields'][det_ch[n]], stats_list[n])
#         print("\n")

#     return stats_list

#*******************************************************************************************************
def dscan(mot, start, stop, steps, det, ct, det_ch=None, md=None):
    """
    Relative scan with live plotting and peak statistics.

    Parameters
    ----------
    mot : OphydObj
        Scanned motor.
    start, stop : float
        Relative scan limits.
    steps : int
        Number of points.
    det : OphydObj
        Main detector to plot.
    ct : float
        Count/exposure time.
    det_ch : list[int] or None
        Detector channels to plot.
        If None:
          - lambda_det -> default lambda_det_stats7_total
          - other detectors -> default channel 0
    md : dict or None
        Extra metadata.
    """
    md = md or {}
    md["count_time"] = ct

    if det_ch is None:
        det_ch = [0]

    dets = [det, det134, sclr.channels.chan13, sr_curr]

    # apply exposure if detector is lambda_det
    if getattr(det, "name", None) == "lambda_det":
        yield from set_lambda_exposure(ct)

    # resolve actual event-data field names to plot/stat
    y_fields = select_detector_fields(det, det_ch)

    # compact legend labels
    legend_keys = {f: short_label(f) for f in y_fields}

    # one live plot callback for all selected fields
    liveplot_cb = CustomLivePlot(
        y_fields=y_fields,
        x=mot.name,
        ax=myaxs,
        legend_keys=legend_keys,
        clear_on_start=True,
        show_stats=True,
        update_every=1,
        title=f"{det.name} vs {mot.name}",
    )

    # one PeakStats per plotted field
    stats_list = [PeakStats(mot.name, field) for field in y_fields]

    subs_list = [liveplot_cb]
    subs_list.extend(stats_list)

    plan = bpp.subs_wrapper(
        bp.rel_scan(dets, mot, start, stop, steps, md=md),
        subs_list,
    )

    yield from plan

    print("\n")
    for field, stats in zip(y_fields, stats_list):
        peaks_stats_print(field, stats)
        print("\n")

    return stats_list

#*******************************************************************************************************
# def ascan(mot, start, stop, steps, det, ct, det_ch=None, md=None):
# # performs relative scan of a detector DET channel 
#     myaxs.clear()
#     # myfig.canvas.draw_idle()

#     if det_ch is None:
#         det_ch = [0]
#     md = md or {}

#     md["count_time"] = ct
#     dets = [det, det134, sclr.channels.chan13, sr_curr]

#     # apply exposure if detector is lambda_det
#     if getattr(det, "name", None) == "lambda_det":
#         yield from set_lambda_exposure(ct)

#     subs_list = [plotselect(det.hints['fields'][det_channel], mot.name) for det_channel in  det_ch]
#     stats_list = [PeakStats(mot.name, det.hints['fields'][det_channel]) for det_channel in det_ch]

#     subs_list.extend(stats_list)
#     plan = bpp.subs_wrapper(bp.scan(dets, mot, start, stop, steps, md=md), subs_list)
        
#     yield from plan

#     for n in range(len(det_ch)):
#         peaks_stats_print(det.hints['fields'][det_ch[n]], stats_list[n])
#         print("\n")
    
#     return stats_list

import bluesky.plans as bp
import bluesky.preprocessors as bpp
from bluesky.callbacks.fitting import PeakStats


#*******************************************************************************************************
def ascan(mot, start, stop, steps, det, ct, det_ch=None, md=None):
    """
    Absolute scan with live plotting and peak statistics.

    Parameters
    ----------
    mot : OphydObj
        Scanned motor.
    start, stop : float
        Absolute scan limits.
    steps : int
        Number of points.
    det : OphydObj
        Main detector to plot.
    ct : float
        Count/exposure time.
    det_ch : int, list[int], or None
        Detector channels to plot.
        If None:
          - lambda_det -> default lambda_det_stats7_total
          - other detectors -> default channel 0
    md : dict or None
        Extra metadata.
    """
    md = md or {}
    md["count_time"] = ct

    if det_ch is None:
        det_ch = [0]

    dets = [det, det134, sclr.channels.chan13, sr_curr]
    # dets = [det]

    # apply exposure if detector is lambda_det
    if getattr(det, "name", None) == "lambda_det":
        yield from set_lambda_exposure(ct)

    # resolve actual event-data field names to plot/stat
    y_fields = select_detector_fields(det, det_ch)
    if not y_fields:
        raise RuntimeError(f"No plot fields resolved for detector {det.name}")

    # compact legend labels
    legend_keys = {f: short_label(f) for f in y_fields}

    # one live plot callback for all selected fields
    liveplot_cb = CustomLivePlot(
        y_fields=y_fields,
        x=mot.name,
        ax=myaxs,
        legend_keys=legend_keys,
        clear_on_start=True,
        show_stats=True,
        update_every=1,
        title=f"{det.name} vs {mot.name}",
    )

    # one PeakStats per plotted field
    stats_list = [PeakStats(mot.name, field) for field in y_fields]

    subs_list = [liveplot_cb]
    subs_list.extend(stats_list)

    plan = bpp.subs_wrapper(
        bp.scan(dets, mot, start, stop, steps, md=md),
        subs_list,
    )

    yield from plan

    print("\n")
    for field, stats in zip(y_fields, stats_list):
        peaks_stats_print(field, stats)
        print("\n")

    return stats_list

#*******************************************************************************************************
def gaussian(x, A, sigma, x0):
    exponent = -(x - x0)**2/(2 * sigma**2)
    # Clip exponent to prevent overflow; exp(-745) ≈ 0, exp(709) ≈ max float
    exponent = np.clip(exponent, -745, 0)
    return A*np.exp(exponent)


#*******************************************************************************************************
def stepup(x, A, sigma, x0, b):
    return A*(1-1/(1+np.exp((x-x0)/sigma)))+b


#*******************************************************************************************************
def stepdown(x, A, sigma, x0, b):
    return A*(1-1/(1+np.exp(-(x-x0)/sigma)))+b


#*******************************************************************************************************
def calc_lmfit(uid=-1, x="hrmE", channel=7):
    # Calculates fitting parameters for Gaussian function for energy scan with UID and Lambda channel
    hdr = db[uid]
    table = hdr.table()
    model = lmfit.Model(gaussian)
    y = f'lambda_det_stats{channel}_total'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.7, 'x0': table[x][table[y].argmax()+1]})
    for name, doc in hdr.documents():
        lf(name, doc)
    gauss = gaussian(table[x], **lf.result.values)
    myaxs.plot(table[x], table[y], label=f"raw, channel={channel}", marker = 'o', linestyle = 'none')
    myaxs.plot(table[x], gauss.values, label=f"gaussian fit {channel}")
    myaxs.legend()

    myaxs.figure.canvas.draw_idle()
    myaxs.figure.canvas.flush_events()

    return lf.result.values


#*******************************************************************************************************
def calc_stepup_fit(x):
    # Calculates fitting parameters for step up function for MCM slits scan
    hdr = db[-1]
    table = hdr.table()
    model = lmfit.Model(stepup)
    y = 'det2_current1_mean_value'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.25, 'x0': 0, 'b':0})
    for name, doc in hdr.documents():
        lf(name, doc)
    print(lf.result.values)
    stup = stepup(table[x], **lf.result.values)
    plt.clf()
    plt.plot(table[x], table[y], label=f"raw data", marker = 'o', linestyle = 'none')
    plt.plot(table[x], stup.values, label=f"data fit")
    plt.legend()
    return lf.result.values['x0']


#*******************************************************************************************************
def calc_stepdwn_fit(x):
    # Calculates fitting parameters for step down function for MCM slits scan
    hdr = db[-1]
    table = hdr.table()
    model = lmfit.Model(stepdown)
    y = 'det2_current1_mean_value'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.25, 'x0': 0, 'b':0})
    for name, doc in hdr.documents():
        lf(name, doc)
    print(lf.result.values)
    stdw = stepdown(table[x], **lf.result.values)
    plt.clf()
    plt.plot(table[x], table[y], label=f"raw data", marker = 'o', linestyle = 'none')
    plt.plot(table[x], stdw.values, label=f"data fit")
    plt.legend()
    return lf.result.values['x0']


#*******************************************************************************************************
def GCarbon_Qscan(exp_time=2):
    # Test plan for the energy resolution at Q=1.2 with the Glassy Carbon
    Qq = [1.2]
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    yield from bps.mv(anapd, 25, whl, 0)
#    myplt = plotselect('lambda_det_stats7_total', hrmE.name)
    myaxs.cla()

    for kk in range(1):
        for q in Qq:
            th = qq2th(q)
            yield from bps.mv(spec.tth, th)
            # yield from set_lambda_exposure(exp_time)
            yield from dscan(hrmE, -10, 10, 100, lambda_det, exp_time)


#*******************************************************************************************************
def DxtalTempCalc(uid=-1):
    """
    Calculates temperature correction for the D crystals.
    
    Parameters
    ----------
    uid : int, optional
          relative scan position in the database
    
    """
    
    E0 = 9131.7     # energy (eV)
    TH = 88.5       # Dxtal asymmetry angle (deg)
    C1 = 3.725e-6   # constant (1/K)
    C2 = 5.88e-3    # constant (1/K)
    C3 = 5.548e-10  # constant (1/K2)
    T1 = 124.0      # temperature (K)
    T0 = 300.15     # crystal average temperature (K)

    bet = C1*(1 - np.exp(-C2*(T0-T1))) + C3*T0
    dE = []
    myaxs.cla()
    for n in range(1,7):
        fit_par = calc_lmfit(uid, channel=n)
        if fit_par['A'] < 100:
            print('**********************************')
            print('         WARNING !')
            print('      Fitting Error')
            return
        
        dE.append(fit_par['x0'])
    
    dE = [x-dE[0] for x in dE]
    dTe = [1.e-3*x/E0/bet for x in dE]
    dTh = [-1.e3*x*np.tan(np.radians(TH))/E0 for x in dE]
    
    DTe = [ura_temp.d1temp.read()['uratemperature_d1temp']['value']+dTe[0], 
           ura_temp.d2temp.read()['uratemperature_d2temp']['value']+dTe[1], 
           ura_temp.d3temp.read()['uratemperature_d3temp']['value']+dTe[2], 
           ura_temp.d4temp.read()['uratemperature_d4temp']['value']+dTe[3], 
           ura_temp.d5temp.read()['uratemperature_d5temp']['value']+dTe[4], 
           ura_temp.d6temp.read()['uratemperature_d6temp']['value']+dTe[5]]
    Dheader = [' ', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6']
    dE.insert(0,'dEnrg')
    dTe.insert(0,'dTemp')
    dTh.insert(0,'dThe')
    DTe.insert(0,'Dtemp')
    Ddata = [dE, dTh, dTe, DTe]
    print('---------------------------------------------------------------------')
    print(tabulate(Ddata, headers=Dheader, tablefmt='pipe', stralign='center', floatfmt='.4f'))
    print('---------------------------------------------------------------------\n')
    print('Select from the following options:')
    print('1. Update temperatures')
    print('2. Update Dxtals angles')
    print('3. Exit without updates')
    update_opts = input('Your choice: ')
    if update_opts == '1':
        ura_temp.d1temp.set(DTe[1])
        ura_temp.d2temp.set(DTe[2])
        ura_temp.d3temp.set(DTe[3])
        ura_temp.d4temp.set(DTe[4])
        ura_temp.d5temp.set(DTe[5])
        ura_temp.d6temp.set(DTe[6])
        print('\n')
        print('The temperatures are updated\n')
    elif update_opts == '2':
        yield from bps.mvr(analyzer_xtals.d2the, dTh[1], analyzer_xtals.d3the, dTh[2], analyzer_xtals.d4the, dTh[3], analyzer_xtals.d5the, dTh[4], analyzer_xtals.d6the, dTh[5],)
        print('\n')
        print('The Dxtals angles are updated\n')
    else:
        print('\n')
        print('Update is canceled\n')
#    return {'dEn':dE, 'dTem':dTe, 'dThe':dTh, 'DTem':DTe}


#*******************************************************************************************************
def ugap_setup():
#   Scans the ID gap and sets it to max
    # det = tm1
    yname = tm1.sum_all.mean_value.name
    res = yield from dscan(ivu22, -20, 20, 21, tm1, 1, det_ch=[4])
    # x_pos = calculate_max_value(x="ivu22", y=yname, sampling=5)
    max_pos = res[0].max
    x_pos = max_pos[0]
    yield from bps.mv(ivu22, x_pos)
    print('\n')
    print('ID gap alignment finished\n')


#*******************************************************************************************************
def crl_setup():
        res = yield from dscan(crl.y, -0.2, 0.2, 20, tm1, 1, det_ch=[4])
        fmax = res[0].max
        xmax = fmax[0]
        yield from bps.mv(crl.y, xmax)


#*******************************************************************************************************
def dcm_setup():
    # Set the DCM position to max intensity
 
    res = yield from dscan(dcm.p1, -80, 80, 40, tm1, 1, det_ch=[4])
    fwhm = res[0].fwhm
    cen  = res[0].cen
    com  = res[0].com
    crs = res[0].crossings

    if fwhm is not None and cen is not None and com is not None and crs is not None:
        if fwhm < 50 and abs(cen - com)/ fwhm < 1 and len(crs) == 2:
            yield from bps.mv(dcm.p1, cen)
            print("DCM moved to center")
        else:
            print("Peak was not found. Motor not moved!")
    else:
        print("Scan did not return valid results. Motor not moved!")


#*******************************************************************************************************
def mcm_setup_prep():
# Prepares the URA for the MCM and Analyzer Slits setup, namely opens the Slits and lowers the analyzer
    hux = hrm2.read()['hrm2_ux']['value']
    hdx = hrm2.read()['hrm2_dx']['value']
    acyy = anc_xtal.y.read()['anc_xtal_y']['value']
    err = 0
    if hux > -5 or hdx > -5:
        print('*************************************\n')
        print('HRM is in the beam. Execution aborted')
        err = 1
        return acyy, err
    airpad.set(1)
    det2.em_range.set(0)
 
    yield from bps.mv(spec.tth, 0)

    yield from bps.mv(anc_xtal.y, 0.5, whl, 2, anpd, 0)
    yield from bps.mv(analyzer_slits.top, 2, analyzer_slits.bottom, -2, analyzer_slits.outboard, 2, analyzer_slits.inboard, -2)
    d21cnt = det2.current1.mean_value.read()['det2_current1_mean_value']['value']
    if d21cnt < 1.0e5:
        print('*************************************\n')
        print('Low intensity on D21. Execution aborted')
        yield from bps.mv(anc_xtal.y, acyy, anpd, -90)
        return
    return acyy, err


#*******************************************************************************************************
def mcm_setup_post(y0):
# Returns the motors to thier previous positions after the MCM and Analyzer Slits setup
    yield from bps.mv(anc_xtal.y, y0, whl, 0, anpd, -90)
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)


#*******************************************************************************************************
def mcm_setup(s1=0, s2=0):
# MCM mirror setup procedure
# Usage:
#       if s1 > 0, then execute mcmx alignment, else - skip it
#       if s2 > 0, then execute mcmy alignment, else - skip it
    MCM_XPOS = -0.941
    if s1 == 0 and s2 == 0:
        print('*************************************\n')
        print('Usage: mcm_setup(s1,s2)')
        print('if s1 > 0, then execute mcmx alignment, else - skip it')
        print('if s2 > 0, then execute mcmy alignment, else - skip it')
        return
    aret = yield from mcm_setup_prep()
    acyy = aret[0]
    if aret[1] > 0:
        return
    if not s1 == 0:
        yield from dscan(mcm.x, -0.2, 0.2, 40, det2, 1)
        x_pos = calculate_max_value(uid=-1, x="mcm_x", y="det2_current1_mean_value", delta=1, sampling=5)
        xmax = x_pos[0]
        dxmax = MCM_XPOS - xmax
        print(f"Maximum position X = {xmax}. Shifted by {dxmax} from the target")
        kc = 1
#        while abs(dxmax) > 1.0e-3:
#        yield from bps.mvr(sample_stage.tx, dxmax)
#        yield from bp.rel_scan([det2], mcm.x, -0.2, 0.2, 41)
#        x_pos = calculate_max_value(uid=-1, x="mcm.x", y="det2_current1_mean_value", delta=1, sampling=100)
#        xmax = x_pos[0]
#        dxmax = MCM_XPOS - xmax
#        print(f"Maximum position X = {xmax}. Shifted by {dxmax} from the target")
#        kc += 1
#        if kc > 5:
#            print("Could not set the MCM_X to maximum. Execution aborted")
#            yield from mcm_setup_post(acyy)
#            break


#*******************************************************************************************************
def analyzer_slit_scan(mtr, start, stop, gaps):
#    plt.clf()
    yield from bps.mv(mtr, 0)
    yield from bp.rel_scan([det2], mtr, start, stop, gaps)
    peak_stats = bec.peaks
    x0 = peak_stats['cen']['det2_current1_mean_value']
    print('*********************\n')
    print(f'{mtr.name} position center {x0}\n')
    if x0 > 1 or x0 < -1:
        print('*********************************************************\n')
        print(f'Verify the {mtr.name} data. Execution aborted!')
    else:
        yield from bps.mv(mtr, x0)
        mtr.set_current_position(0)


#*******************************************************************************************************
def san_setup():
#    acyy = ura_setup_prep()
    yield from analyzer_slit_scan(analyzer_slits.outboard, -1.2, 1.2, 41)
    yield from bps.mv(analyzer_slits.outboard, 2)

    yield from analyzer_slit_scan(analyzer_slits.inboard, -1.2, 1.2, 41)
    yield from bps.mv(analyzer_slits.inboard, -2)

    yield from analyzer_slit_scan(analyzer_slits.top, -1., 1., 41)
    yield from bps.mv(analyzer_slits.top, 2)
    
    yield from analyzer_slit_scan(analyzer_slits.bottom, -1., 1., 41)
    yield from bps.mv(analyzer_slits.bottom, -2)
    
#    ura_setup_post(acyy)
    print('*****************************************\n')
    print("Analyzer slits setup finished successfully\n")


#*******************************************************************************************************
def calculate_max_value(uid=-1, x="hrmE", y="lambda_det_stats7_total", delta=1, sampling=200):
    """
    This method gets a table (DataFrame) by using its uid. it finds the maximum value of the curve 
    under the sampled data by using the maximum y value and its neighboring data samples and then, 
    applying a polynomial regression over this curve. The model is used as an interpolation approach
    to generate more points between the original range and to return the x and y values of the
    maximum point of this new model

    Parameters
    ----------
    uid : int, optional
        id of the scan. The default is -1.
    x : str, optional
        label of the x values in the table. The default is "hrmE".
    channel : str, optional
        value of the channel with the y values. The default is 7.
    delta : int, optional
        total of points to be used on each side of the maximum value to generate the new model. The default is 1.
    sampling : int, optional
        total of sampling points to be used for interpolation. The default is 200.

    Raises
    ------
    ValueError
        The selected delta value is too big to be used based on the position of the maximum value in the table.

    Returns
    -------
    flaot
        x value of the maximum value.
    float
        y value of the maximum value.

    """

    hdr = db[uid]
    table = hdr.table()
    #y = f'lambda_det_stats{channel}_total'
    
    #cp_df = df.copy()
    
    max_id = table[y].idxmax()
    
    # low limit check
    if max_id >= delta:
        low_max_id = max_id - delta
    else:
        raise ValueError("Delta value is greater than the lower limit of the dataset")
    
    # high limit check
    if max_id < len(table[y])-delta-1:
        high_max_id = max_id + delta + 1
    else:
        raise ValueError("Delta value is greater than the upper limit of the dataset")
    
    y_values = table[y][low_max_id:high_max_id]
    x_values = table[x][low_max_id:high_max_id]
    
    model = np.poly1d(np.polyfit(x_values, y_values, 2))
    
    resampled_x_values = np.linspace(x_values.iloc[0],x_values.iloc[-1],sampling)
    resampled_y_values = model(resampled_x_values)
    
    resample_df = pd.DataFrame({x:resampled_x_values, y:resampled_y_values})
    
    new_max_id = resample_df[y].idxmax()
    
    return resample_df[x][new_max_id], resample_df[y][new_max_id]


#*******************************************************************************************************
def LocalBumpSetup(silent=False):
    """
    Adjusts the e-beam local bump, i.e. horizontal & vertical positions of the x-ray beam on the XBPM1 screen

    """
    
    cond1 = strg_ring_orb_fb.uofb_pv.read()['srofb_uofb_pv']['value']
    cond2 = strg_ring_orb_fb.id_bump_pv.read()['srofb_id_bump_pv']['value']
    cond3 = strg_ring_orb_fb.nudge_pv.read()['srofb_nudge_pv']['value']
    pos3 = 0
    pos5 = 49
    cenX_target = 387
    cenY_target = 904

    if cond1 != 2:
        print("****************** WARNING ******************")
        print("The UOFB is disabled. Operation is terminated")
        return
    if cond2 != 1:
        print("****************** WARNING ******************")
        print("The ID Bump is disabled. Operation is terminated")
        return
    if cond3 != 1:
        print("****************** WARNING ******************")
        print("The Nudge is disabled. Operation is terminated")
        return

    yield from bps.mv(bpm1_diag, pos5)
    cam1.cam.acquire_time.set(0.0002)
    cam1.cam.acquire_period.set(0.5)
    cam1.cam.num_images.set(1)
    cam1.cam.image_mode.set(2)
    cam1.cam.acquire.set(1)
    cam1.stats1.enable.set(1)
    cam1.stats1.compute_statistics.set(1)
    cam1.stats1.compute_centroid.set(1)
    Imax = cam1.stats1.max_value.get()
    if Imax < 2000:
        print('********************************')
        print('Low image intensity')
        print('Execution is terminated')
        return
    
    cam1.stats1.centroid_threshold.set(1000)
    centr = cam1.stats1.centroid.get()
    print(f'centroid X = {centr[1]:.2f}, target X = {cenX_target}\n')
    cenX = centr[1]
    dXc = cenX - cenX_target
    dThe = 1.e-3*dXc/6.0
    if abs(dThe) < 0.01:
        print(f"Calculated horizontal e-beam shift {1.e3*dThe:0.1f} urad")
        if not silent:
            input_opts = input('Do you want to put it in (yes/no): ')
        else:
            input_opts = 'yes'
        
        if input_opts == 'yes':
            strg_ring_orb_fb.nudge_increment.set(dThe)
            strg_ring_orb_fb.horz_plane_nudge.set(1)
            yield from sleep(2)
            print('*****************************************')
            xtarget = strg_ring_orb_fb.xa_rbv.read()
            valx = 1.e3*xtarget['srofb_xa_rbv']['value']
            print(f'Horizontal angle correction was applied. New value {valx:0.1f} urad\n')
            print(strg_ring_orb_fb.nudge_status.alarm_status)
        else:
            print('*****************************************')
            print('Correction was canceled\n')

    crl_y_pos = crl.read()['crl_y']['value']
    if crl_y_pos < 1:
        print('\n')
        print('Error: CRL is in the x-ray beam. Vertical beam correction is canceled.\n')
        return
    
    print(f'centroid Y = {centr[0]:.2f}, target Y = {cenY_target}\n')
    cenY = centr[0]
    dYc = cenY - cenY_target
    dThe = -1.e-3*dYc/5.0
    if abs(dThe) < 0.01:
        print(f"Calculated vertical e-beam shift {1.e3*dThe:0.1f} urad")
        if not silent:
            input_opts = input('Do you want to put it in (yes/no): ')
        else:
            input_opts = 'yes'
        
        if input_opts == 'yes':
            strg_ring_orb_fb.nudge_increment.set(dThe)
            strg_ring_orb_fb.vert_plane_nudge.set(1)
            yield from sleep(2)
            print('*****************************************')
            ytarget = strg_ring_orb_fb.xy_rbv.read()
            valy = 1.e3*ytarget['srofb_xy_rbv']['value']
            print(f'Vertical angle correction was applied. New value {valy:0.1f} urad\n')
            print(strg_ring_orb_fb.nudge_status.alarm_status)
        else:
            print('*****************************************')
            print('Correction was canceled\n')

    if not silent:
        update_opts = input('Do you want to move the XBPM1 back (yes/no): ')
    else:
        update_opts = 'yes'
    
    if update_opts == 'yes':
        cam1.cam.acquire.set(0)
        yield from bps.mv(bpm1_diag, pos3)


#*******************************************************************************************************
def ccr_setup_prep():
# Prepares the URA for the C crystal setup
    hux = hrm2.read()['hrm2_ux']['value']
    hdx = hrm2.read()['hrm2_dx']['value']
    err = 0
    if hux > -5 or hdx > -5:
        print('*************************************')
        print('Error: HRM is in the beam. Execution aborted\n')
        err = 1
        return err
    
    airpad.set(1)
    det2.em_range.set(0)
    yield from bps.mv(spec.tth, 0)
    acyy = anc_xtal.read()['anc_xtal_y']['value']
    if acyy < 5:
        print('*************************************')
        print('Error: URA Y-position (acyy) is too low. Execution aborted\n')
        err = 1
        return err

    yield from bps.mv(analyzer_slits.top, 0.1, analyzer_slits.bottom, -0.1, analyzer_slits.outboard, 1, analyzer_slits.inboard, -1)
    d21cnt = det2.current1.mean_value.read()['det2_current1_mean_value']['value']
    if d21cnt < 1.0e5:
        print('****************************************')
        print('Error: low intensity on D21. Execution aborted\n')
        yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
        err = 1
        return err
    return err

#*******************************************************************************************************
def ccr_setup_post():
#   Recover positions after the C crystal alignment is finished
    yield from bps.mv(anpd, -90, analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    

#*******************************************************************************************************
def ccr_the_setup():
#   Performs C crystal theta alignment
    x0 = 10
    kxmov = 0
    while abs(x0) > 5 and kxmov < 5:
        yield from bp.rel_scan([det2], analyzer.cfth, -150, 150, 31)
        peak_stats = bec.peaks
        x0 = peak_stats['cen']['det2_current1_mean_value']
        x_deg = -np.rad2deg(1.e-6*x0)
        yield from bps.mvr(anc_xtal.the, x_deg)
        kxmov += 1

    return kxmov


#*******************************************************************************************************
def ccr_setup(s1=0, s2=0, s3=0):
#   C crystal alignment, namely the-position, analyzer vertical position and chi-position
    
    if s1 == 0 and s2 == 0 and s3 == 0:
        print("\n")
        print("Usage: ccr_setup(s1, s2, s3)")
        print("if s1 > 0, then execute acthe alignment, else - skip")
        print("if s2 > 0, then execute acyy alignment, else - skip")
        print("if s3 > 0, then execute cchi alignment, else - skip")
        return
    
    ret = yield from ccr_setup_prep()
    if ret > 0:
        return
    
    # C crystal Theta alignment
    if s1 != 0:
        print('\n')
        print('Setting up the C crystal The-position\n')
        det2.em_range.set(0)
        sleep(1)
        yield from bps.mv(whl, 0, anpd, 40)
        kxmov = yield from ccr_the_setup()
        if kxmov > 5:
            print('\n')
            print('************************************')
            print('Error: C crystal The-positioning. Execution aborted\n')
            return
        
    # C crystal Y alignment
    if s2 != 0:
        print('\n')
        print('Setting up the C crystal Y-position\n')
        det2.em_range.set(1)
        sleep(1)
        yield from bps.mv(whl, 2, anpd, -145)
        yield from bps.mv(analyzer_slits.top, 0.04, analyzer_slits.bottom, -0.04)
        yield from bp.rel_scan([det2], anc_xtal.y, -0.3, 0.3, 61)
        peak_stats = bec.peaks
        p_max = peak_stats['max']['det2_current1_mean_value'][1]
        p_min = peak_stats['min']['det2_current1_mean_value'][1]
        dp = p_max - p_min
        if dp < 1.e3:
            print('\n')
            print('Error: acyy position maximum not found. Execution aborted\n')
            yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1)
            return
        
        p_com = peak_stats['com']['det2_current1_mean_value']
        yield from bps.mv(anc_xtal.y, p_com)
        yield from bps.mv(analyzer_slits.top, 0.1, analyzer_slits.bottom, -0.1)

    # C crystal Chi alignment
    if s3 != 0:
        print('\n')
        print('Setting up the C crystal Chi-position\n')
        yield from bps.mv(whl, 0, anpd, -145)
        det2.em_range.set(0)
        sleep(1)
        yield from bps.mvr(anc_xtal.y, 0.6)
        yield from bps.mv(analyzer_slits.outboard, 0.5, analyzer_slits.inboard, -0.5)
        d22cnt = det2.current2.mean_value.read()['det2_current2_mean_value']['value']
        if d22cnt < 1.e5:
            print('\n')
            print('Error: low intensity on d22. Verify acchi manually. Execution aborted\n')
            return
        
        yield from bp.rel_scan([det2], analyzer.cchi, -0.15, 0.15, 31)
        yield from bps.mvr(analyzer.cchi, -0.15)
        peak_stats = bec.peaks
        x0 = peak_stats['cen']['det2_current2_mean_value']
        yield from bps.mv(analyzer.cchi, x0)
        yield from bps.mv(analyzer_slits.outboard, 1, analyzer_slits.inboard, -1)

        # Re-checking C crystal The-position

        yield from bps.mv(anpd, 40)
        kxmov = yield from ccr_the_setup()
        if kxmov > 5:
            print('\n')
            print('************************************')
            print('Error: C crystal The-positioning. Execution aborted\n')
            return
        
    yield from ccr_setup_post
    print('\n')
    print('C crystal alignment finished\n')


#*******************************************************************************************************
def wcr_setup():
#   Performs W crystal alignment
    yield from bps.mv(anpd, -90, whl, 7, analyzer_slits.top, 0.1, analyzer_slits.bottom, -0.1, analyzer_slits.outboard, 1, analyzer_slits.inboard, -1)
    # yield from set_lambda_exposure(1)
    # yield from bp.rel_scan([lambda_det], analyzer.wfth, -20, 20, 41)
    yield from dscan(analyzer.wfth, -20, 20, 41, lambda_det, 1)
    x_pos = calculate_max_value(x="analyzer.wfth", sampling=100)
    yield from bps.mvr(analyzer.wfth, -20)
    yield from bps.mv(analyzer.wfth, x_pos)
    print('\n')
    print('W crystal alignment finished\n')


#*******************************************************************************************************
def hrm_in():
#   Moves HRM into the x-ray beam
    yield from bps.mv(hrm2.ux, 0, hrm2.dx, 0, hrm2.bs, 3)


#*******************************************************************************************************
def hrm_out():
#   Moves HRM out of the x-ray beam
    yield from bps.mv(hrm2.ux, -20, hrm2.dx, -20, hrm2.bs, 0)


#*******************************************************************************************************
def hrm_setup():
#   Performs HRM crystals alignment
    det4.em_range.set(0)
    det4.acquire_mode.set(0)
    det4.averaging_time.set(0.5)
    det5.em_range.set(0)
    det5.acquire_mode.set(0)
    det5.averaging_time.set(0.5)
    sleep(1)

    yield from hrm_in()
    yield from bps.mv(hrmE, 0, hrm2.d1, 0)
    yield from bps.mv(s1.top, 0.5, s1.bottom, -0.5, s1.outboard, 1, s1.inboard, -1)
    yield from bps.mv(hrm2.d2, 1, hrm2.d4, 0.7)
    yield from bps.mv(hrm2.d3, 2, hrm2.d5, 2)
    
    # 1st crystal alignment
    yield from bp.rel_scan([det4], hrm2.uth, -0.05, 0.05, 51)
    peak_stats = bec.peaks
    x_com = peak_stats['com']['det4_current2_mean_value']
    x_cen = peak_stats['cen']['det4_current2_mean_value']
    x_fwhm = peak_stats['fwhm']['det4_current2_mean_value']
    if abs(x_com-x_cen)/x_fwhm > 0.3:
        print('\n')
        print('Error: 1st crystal peak not found. Execution terminated.\n')
        return
    yield from bps.mv(hrm2.uth, x_cen, hrm2.d2, 0)

    # 2nd crystal alignment
    yield from bp.rel_scan([det4], hrm2.uif, -70, 70, 51)
    peak_stats = bec.peaks
    x_com = peak_stats['com']['det4_current3_mean_value']
    x_cen = peak_stats['cen']['det4_current3_mean_value']
    x_fwhm = peak_stats['fwhm']['det4_current3_mean_value']
    if abs(x_com-x_cen)/x_fwhm > 0.3:
        print('\n')
        print('Error: 2nd crystal peak not found. Execution terminated.\n')
        return
    yield from bps.mv(hrm2.uif, x_cen, hrm2.d3, 0)

    # 3rd crystal alignment
    yield from bp.rel_scan([det4], hrm2.dth, -0.01, 0.01, 51)
    peak_stats = bec.peaks
    x_com = peak_stats['com']['det4_current4_mean_value']
    x_cen = peak_stats['cen']['det4_current4_mean_value']
    x_fwhm = peak_stats['fwhm']['det4_current4_mean_value']
    if abs(x_com-x_cen)/x_fwhm > 0.3:
        print('\n')
        print('Error: 3rd crystal peak not found. Execution terminated.\n')
        return
    yield from bps.mv(hrm2.dth, x_cen, hrm2.d4, 0)

    # 4th crystal alignment
    yield from bp.rel_scan([det5], hrm2.dif, -70, 70, 51)
    peak_stats = bec.peaks
    x_com = peak_stats['com']['det5_current1_mean_value']
    x_cen = peak_stats['cen']['det5_current1_mean_value']
    x_fwhm = peak_stats['fwhm']['det5_current1_mean_value']
    if abs(x_com-x_cen)/x_fwhm > 0.3:
        print('\n')
        print('Error: 4th crystal peak not found. Execution terminated.\n')
        return
    yield from bps.mv(hrm2.dif, x_cen, hrm2.d5, 0)


#*******************************************************************************************************
def DxtalMesh(cnum=4, whl_pos=6, ctime=1):
    """
    Performs mesh scan of the analyzer D crystals: analyzer vertical position versus energy.
    
    Parameters
    -----------
    cnum    : int, optional
              number of measurements cycles
    whl_pos : int, optional
              position of the whl wheel
    ctime   : int, optional
              counting time for lambda detector
    
    """

    spec_factory.prefix = "mesh_scan"
    yield from bps.mv(whl, whl_pos, spec.tth, 0)
    yield from bps.mv(analyzer_slits.top, 0.01, analyzer_slits.bottom, -0.01, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    yield from bps.mv(mcm_slits.outboard, 1.0, mcm_slits.inboard, -1.0)
    yield from set_lambda_exposure(ctime)
    acyy = anc_xtal.y.read()['anc_xtal_y']['value']
    hrmE_val = hrmE.read()['hrmE']['value']
#    print(acyy, hrmE_val)
    bec.enable_plots()
#    subs = [LiveGrid((150, 100), 'lambda_det_md7', xlabel='Energy', ylabel='acyy', ax=myaxs)]
#    plan = bpp.subs_wrapper(bp.rel_grid_scan([lambda_det], anc_xtal.y, -0.875, 0.625, 150, hrmE, -10, 10, 100, False), subs)
    for n in range(cnum):
        yield from bp.rel_grid_scan([lambda_det], anc_xtal.y, -0.875, 0.625, 150, hrmE, -10, 10, 100, False)
#        yield from plan
        sleep(600)
        
#    LiveGrid((150, 100), 'lambda_det_md7')
    bec.disable_plots()

#*******************************************************************************************************

def Beamline_Setup_1():
    # Performs 10-ID optics alignment down to the sample position
    #
    # 1. Move CRL to bypass position and wait for a few minutes for DCM to warm up.
    #
    print("Moving CRL out of the beam")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from bps.mv(crl.y, 35.17)
        yield from sleep(2)
        print("CRL is out of the beam")
        cont_opts = input('Do you want to continue (yes): ')
        print(cont_opts)
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 2. Check intensity at TM1 detector
    #
    counts = tm1.sum_all.mean_value.get()
    if counts < 1.0e-6:
        print("Low intensity at TM1 detector. Execution terminated")
        return
    #
    # 3. DCM setup
    #
    print("DCM setup")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from dcm_setup()
        yield from sleep(2)
        print("DCM setup is done")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 4. UGAP setup
    #
    print("Undulator gap setup")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from ugap_setup()
        yield from sleep(2)
        print("Undulator gap setup is done")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 5. Local bump setup
    #
    print("Local bump setup")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from LocalBumpSetup(silent=True)
        yield from sleep(2)
        print("Local bump setup is done")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 6. Move CRL to the focusing position and wait for a few minutes for DCM to warm up.
    #
    print("Moving CRL into the beam")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from bps.mv(crl.y, 0.427)
        yield from sleep(2)
        print("CRL is in the beam")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 7. DCM setup
    #
    print("DCM setup")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from dcm_setup()
        yield from sleep(2)
        print("DCM setup is done")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
        #
    # 8. CRL setup scan. Set CRL y-position to max intensity at TM1
    #
    print("CRL setup")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        # res = yield from dscan(crl.y, -0.2, 0.2, 20, tm1, 1, det_ch=[4])
        # fmax = res[0].max
        # xmax = fmax[0]
        yield from crl_setup()
        print("CRL setup is done")
        cont_opts = input('Do you want to continue (yes): ')
        if cont_opts != "" and cont_opts != "yes":
            return
    #
    # 9. Move HRM out of the beam
    #
    print("Moving HRM out of the beam")
    cont_opts = input('Do you want to proceed (yes): ')
    if cont_opts == "" or cont_opts == "yes":
        yield from hrm_out()
    
    print("Beamline setup 1 is completed successfully")