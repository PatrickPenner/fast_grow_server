"""fast_grow celery tasks"""
import logging
from celery import shared_task
from .tool_wrappers.preprocessor_wrapper import PreprocessorWrapper
from .tool_wrappers.clipper_wrapper import ClipperWrapper
from .tool_wrappers.fast_grow_wrapper import FastGrowWrapper
from .models import Complex, Core, Status, Growing


@shared_task
def preprocess_complex(complex_id):
    """preprocess a complex model using the preprocessor binary"""
    cmplx = Complex.objects.get(id=complex_id)
    try:
        PreprocessorWrapper.preprocess(cmplx)
        cmplx.status = Status.SUCCESS
        cmplx.save()
    except Exception as error:
        logging.error(error)
        cmplx.status = Status.FAILURE
        cmplx.save()
        raise error


@shared_task
def clip_ligand(core_id):
    """clip a ligand into a core"""
    core = Core.objects.get(id=core_id)
    try:
        ClipperWrapper.clip(core)
        core.status = Status.SUCCESS
        core.save()
    except Exception as error:
        logging.error(error)
        core.status = Status.FAILURE
        core.save()
        raise error


@shared_task
def grow(growing_id):
    """perform a growing"""
    growing = Growing.objects.get(id=growing_id)
    try:
        FastGrowWrapper.grow(growing)
        growing.status = Status.SUCCESS
        growing.save()
    except Exception as error:
        logging.error(error)
        growing.status = Status.FAILURE
        growing.save()
        raise error
