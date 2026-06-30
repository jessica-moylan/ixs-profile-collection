from ophyd.areadetector.cam import Lambda750kCam
from ophyd import Component as Cpt
from ophyd import ROIPlugin, TransformPlugin, EpicsSignal, EpicsSignalRO
from ophyd.areadetector.base import EpicsSignalWithRBV as SignalWithRBV
from ophyd.areadetector.cam import CamBase
from ophyd.areadetector import ADComponent as ADCpt, DetectorBase
from nslsii.ad33 import StatsPluginV33, SingleTriggerV33
from ophyd.areadetector.plugins import PluginBase


class PluginCV(PluginBase):
    comp_vision_function1 = ADCpt(EpicsSignal, 'CompVisionFunction1')
    input1 = ADCpt(EpicsSignal, 'Input1')

class LambdaDetector(DetectorBase):
    _html_docs = ['lambda.html']
    cam = Cpt(Lambda750kCam, 'cam1:')

class Lambda(SingleTriggerV33, LambdaDetector):
    # MR20200122: created all dirs recursively in /nsls2/jpls/data/lambda/
    # from 2020 to 2030 with 777 permissions, owned by xf12id1 user.
    # tiff = Cpt(TIFFPluginWithFileStore,
    #            suffix="TIFF1:",
    #            write_path_template="/nsls2/xf12id1g/data/lambda/%Y/%m/%d/",
    #            read_path_template="/nsls2/xf12id1g/data/lambda/%Y/%m/%d/",
    #            root='/nsls2/xf12id1g/data') 
    cv1 = Cpt(PluginCV, 'CV1:')
    
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    roi5 = Cpt(ROIPlugin, 'ROI5:')
    roi6 = Cpt(ROIPlugin, 'ROI6:')
    roi7 = Cpt(ROIPlugin, 'ROI7:')


    stats1 = Cpt(StatsPluginV33, 'Stats1:', read_attrs=['total'])
    stats2 = Cpt(StatsPluginV33, 'Stats2:', read_attrs=['total'])
    stats3 = Cpt(StatsPluginV33, 'Stats3:', read_attrs=['total'])
    stats4 = Cpt(StatsPluginV33, 'Stats4:', read_attrs=['total'])
    stats5 = Cpt(StatsPluginV33, 'Stats5:', read_attrs=['total'])
    stats6 = Cpt(StatsPluginV33, 'Stats6:', read_attrs=['total'])
    stats7 = Cpt(StatsPluginV33, 'Stats7:', read_attrs=['total'])


    trans1 = Cpt(TransformPlugin, 'Trans1:')

    low_thr = Cpt(EpicsSignal, 'cam1:LowEnergyThreshold')
    hig_thr = Cpt(EpicsSignal, 'cam1:HighEnergyThreshold')
    oper_mode = Cpt(EpicsSignal, 'cam1:OperatingMode')

lambda_det = Lambda('XF:10IDC-BI{Lambda-Cam:1}', name='lambda_det')
for j in range(1, 8):
    getattr(lambda_det, f'stats{j}').kind = 'normal'
lambda_det.stats7.total.kind = 'hinted'


# Impose Stats4 to be ROI4 if in the future we need to exclude bad pixels
def set_defaut_stat_roi():
    yield from bps.mv(lambda_det.stats1.nd_array_port, 'ROI1')
    yield from bps.mv(lambda_det.stats2.nd_array_port, 'ROI2')
    yield from bps.mv(lambda_det.stats3.nd_array_port, 'ROI3')
    yield from bps.mv(lambda_det.stats4.nd_array_port, 'ROI4')


def set_lambda_exposure(exposure):
    # Sets the Lambda detector exposure time (exposure)
    det = lambda_det
    yield from bps.mv(det.cam.acquire_time, exposure, det.cam.acquire_period, exposure)


def setup_lambda_detector():
    """Configure the Lambda detector for standard use.

    Applies settings and verifications in the order of the standard setup procedure:

    Phase 1 - ContinuousReadWrite mode (steps 1-6):
        AcquireTime=1s, AcquirePeriod=1s, LowEnergyThreshold=4.5 keV,
        OperatingMode=ContinuousReadWrite. Verifies 1 image per acquisition
        and that ArrayCounter increments.

    Phase 2 - DualThreshold mode (steps 7-10):
        OperatingMode=DualThreshold, LowEnergyThreshold=4.5 keV,
        HighEnergyThreshold=11.0 keV. Verifies 2 images per acquisition.

    Phase 3 - ADCompVision + final verification (steps 12-16):
        CV1:CompVisionFunction1=Subtract, CV1:Input1=1.
        Verifies 2 images per acquisition and that ArrayCounter increments.

    Raises RuntimeError if any verification step fails.
    """
    det = lambda_det

    # Step 1
    yield from bps.mv(det.cam.acquire_time, 1)
    # Step 2
    yield from bps.mv(det.cam.acquire_period, 1)
    # Step 3
    yield from bps.mv(det.low_thr, 4.5)
    # Step 5
    yield from bps.mv(det.oper_mode, 'ContinuousReadWrite')

    # Step 4: verify 1 image per acquisition in ContinuousReadWrite mode
    yield from bps.abs_set(det.cam.acquire, 1, wait=False)
    yield from bps.sleep(2)
    num_images = det.cam.num_images_counter.get()
    if num_images != 1:
        raise RuntimeError(
            f"Step 4 failed: expected 1 image per acquisition, got {num_images}."
        )

    # Step 6: verify ArrayCounter increments with each acquisition
    counter_before = det.cam.array_counter.get()
    yield from bps.abs_set(det.cam.acquire, 1, wait=False)
    yield from bps.sleep(2)
    counter_after = det.cam.array_counter.get()
    if counter_after <= counter_before:
        raise RuntimeError(
            f"Step 6 failed: ArrayCounter did not increase "
            f"(before={counter_before}, after={counter_after})."
        )

    # Step 7
    yield from bps.mv(det.oper_mode, 'DualThreshold')
    # Step 8
    yield from bps.mv(det.low_thr, 4.5)
    # Step 9
    yield from bps.mv(det.hig_thr, 11.0)

    # Step 10: verify 2 images per acquisition in DualThreshold mode
    yield from bps.abs_set(det.cam.acquire, 1, wait=False)
    yield from bps.sleep(2)
    num_images = det.cam.num_images_counter.get()
    if num_images != 2:
        raise RuntimeError(
            f"Step 10 failed: expected 2 images per acquisition in DualThreshold mode, "
            f"got {num_images}."
        )

    # Step 12
    yield from bps.mv(det.cv1.comp_vision_function1, 'Subtract')
    # Step 13
    yield from bps.mv(det.cv1.input1, 1)

    # Step 15: verify 2 images per acquisition after CV configuration
    yield from bps.abs_set(det.cam.acquire, 1, wait=False)
    yield from bps.sleep(2)
    num_images = det.cam.num_images_counter.get()
    if num_images != 2:
        raise RuntimeError(
            f"Step 15 failed: expected 2 images per acquisition after CV setup, "
            f"got {num_images}."
        )

    # Step 16: verify ArrayCounter increments after CV configuration
    counter_before = det.cam.array_counter.get()
    yield from bps.abs_set(det.cam.acquire, 1, wait=False)
    yield from bps.sleep(2)
    counter_after = det.cam.array_counter.get()
    if counter_after <= counter_before:
        raise RuntimeError(
            f"Step 16 failed: ArrayCounter did not increase "
            f"(before={counter_before}, after={counter_after})."
        )

