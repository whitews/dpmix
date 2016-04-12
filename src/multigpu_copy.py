"""
Written by: Andrew Cron
"""

from mpi4py import MPI
import numpy as np
from utils import MCMC_Task
import gpustats
import gpustats.util as gpu_util
import gpustats.sampler as gpu_sampler
from pycuda.gpuarray import to_gpu
import cuda_functions


# Multi GPU
_datadevmap = {}
_dataind = {}


def init_GPUWorkers(data, device_number):
    """
    Send data to GPU device
    """

    gpu_util.threadSafeInit(device_number)
    gpu_data = []

    # dpmix and BEM
    if type(data) == np.ndarray:
        gpu_data.append(to_gpu(np.asarray(data, dtype=np.float32)))
    else:  # HDP...one or more data sets per GPU
        for i in xrange(len(data)):
            gpu_data.append(to_gpu(np.asarray(data[i], dtype=np.float32)))

            _dataind[i] = i  # not sure if this is correct
            _datadevmap[i] = 0  # or this

    return gpu_data


def get_hdp_labels_GPU(gpu_data, w, mu, Sigma, relabel=False):

    labels = []
    Z = []

    for i, data_set in enumerate(gpu_data):
        densities = gpustats.mvnpdf_multi(
            data_set,
            mu,
            Sigma,
            weights=w[i].flatten(),
            get=False,
            logged=True,
            order='C'
        )

        if relabel:
            Z.append(
                np.asarray(
                    cuda_functions.gpu_apply_row_max(densities)[1].get(),
                    dtype='i'
                )
            )
        else:
            Z.append(None)

        labels.append(
            np.asarray(
                gpu_sampler.sample_discrete(densities, logged=True),
                dtype='i'
            )
        )

        densities.gpudata.free()
        del densities

    return labels, Z 


def get_labelsGPU(gpu_data, w, mu, Sigma, relabel=False):
    densities = gpustats.mvnpdf_multi(
        gpu_data[0],
        mu,
        Sigma,
        weights=w.flatten(),
        get=False,
        logged=True,
        order='C'
    )

    if relabel:
        Z = np.asarray(
            cuda_functions.gpu_apply_row_max(densities)[1].get(),
            dtype='i'
        )
    else:
        Z = None

    labels = np.asarray(
        gpu_sampler.sample_discrete(densities, logged=True),
        dtype='i'
    )

    densities.gpudata.free()
    del densities

    return labels, Z


def get_expected_labels_GPU(gpu_data, w, mu, Sigma):
    densities = gpustats.mvnpdf_multi(
        gpu_data[0],
        mu,
        Sigma,
        weights=w.flatten(),
        get=False,
        logged=True,
        order='C'
    )

    dens = np.asarray(densities.get(), dtype='d')

    densities.gpudata.free()
        
    return dens


def kill_GPUWorkers(workers):
    # poison pill to each child
    ndev = workers.remote_group.size
    msg = np.array(-1, dtype='i')
    for i in xrange(ndev):
        workers.Isend([msg, MPI.INT], dest=i, tag=11)
    workers.Disconnect()
