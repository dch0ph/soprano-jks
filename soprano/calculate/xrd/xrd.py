"""
Classes and functions for simulating X-ray diffraction
spectroscopic results from structures.
"""

# Python 2-to-3 compatibility code
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import copy
import inspect
import numpy as np
from pyspglib import spglib
from collections import namedtuple
# Internal imports
from soprano import utils
from soprano.calculate.xrd import sel_rules as xrdsel

XraySpectrum = namedtuple("XraySpectrum", ("theta2", "hkl", "hkl_unique",
                                           "invd", "intensity", "lambdax"))

XraySpectrumData = namedtuple("XraySpectrumData", ("theta2", "intensity"))


class XRDCalculator(object):

    """A class implementing methods for XRD simulations, comparisons and
    fittings.

    """

    def __init__(self, lambdax=1.54056, theta2_digits=6, baseline=0.0,
                 peak_func=None, peak_f_args=None):
        """
        Initialize the XDRCalculator object's main parameters

        | Args:
        |    lambdax (Optional[float]): X-ray wavelength in Angstroms
        |                               (default is 1.54056 Ang)
        |    theta2_digits (Optional[int]): Rounding within which
        |                                  two theta angles (in degrees)
        |                                  are considered to be equivalent
        |                                  (default is 6 digits) when
        |                                  calculating theoretical peaks
        |   baseline (Optional[float]): baseline to use as starting point for
        |                               simulated spectra
        |   peak_func (Optional[function<float, float, *kargs>
        |                       => <np.ndarray>]): the function used to
        |                                          simulate peaks. Should take
        |                                          th2 as its first argument,
        |                                          peak centre as its second,
        |                                          and any number of optional
        |                                          arguments. Returns a numpy
        |                                          array containing the peak
        |                                          shape. Should be able to
        |                                          work with numpy arrays as
        |                                          input
        |   peak_f_args (Optional[list<float>]): optional arguments for
        |                                        peak_func. If no peak_func
        |                                        has been supplied by the
        |                                        user, the first value will
        |                                        be used as the Gaussian width

        """

        # These properties are basic and can be changed by the user directly
        self.lambdax = lambdax
        self.theta2_digits = 6
        self.baseline = baseline
        # These ones not so much and need checking
        self.set_peak_func(peak_func, peak_f_args)

    @property
    def peak_func(self):
        """The function used to build peaks in simulated spectra

           Should be of form peak_func(theta2, peak_position, *peak_f_args)

        """
        return self._peak_func

    @property
    def peak_f_args(self):
        """Additional arguments to be passed to peak_func"""
        return self._peak_f_args

    # The setter isn't part of the property because the option to pass None
    # has to be made clear as well
    def set_peak_func(self, peak_func=None, peak_f_args=None):
        """Set a new peak_func for this XDRCalculator. If no new function is
           passed, reset the default Gaussian function.

           | Args:
           |   peak_func (Optional[function<float, float, *kargs>
           |                       => <np.ndarray>]): the function used to
           |                                          simulate peaks. Should
           |                                          take th2 as its first
           |                                          argument, peak centre as
           |                                          its second, and any
           |                                          number of optional
           |                                          arguments. Returns a
           |                                          numpy array containing
           |                                          the peak shape. Should
           |                                          be able to work with
           |                                          numpy arrays as input
           |   peak_f_args (Optional[list<float>]): optional arguments for
           |                                        peak_func. If no peak_func
           |                                        has been supplied by the
           |                                        user, the first value will
           |                                        be used as the Gaussian
           |                                        width
        """

        # If there's no peak function args...
        if peak_f_args is None:
            if peak_func is not None:
                peak_f_args = []
            else:
                peak_f_args = [0.1]  # Default Gaussian width

        # For peak_func there's little we can do to check, mostly it's the
        # user's responsibility.
        if peak_func is not None:
            argspec = inspect.getargspec(peak_func)
            nargs = len(argspec.args)
            nargs_def = 0 if argspec.defaults is None else len(
                argspec.defaults)
            if nargs < 2:
                raise ValueError("Invalid peak_func passed to set_peak_func")
            elif (nargs-(2+nargs_def)) > len(peak_f_args):
                raise ValueError("""Invalid number of peak_f_args passed to
                                    set_peak_func""")
        else:
            # A gaussian here
            peak_func = _gauss_peak_default
            if peak_f_args is None:
                # Use default width
                peak_f_args = [0.1]
            else:
                peak_f_args = peak_f_args[:1]  # Ignore all args but one

        self._peak_func = peak_func
        self._peak_f_args = peak_f_args

    def powder_peaks(self, atoms=None, latt_abc=None, n=1, o='all'):
        """
        Calculate the peaks (without intensities) of a powder
        XRD spectrum given either an Atoms object or the lattice in ABC form
        and the spacegroup indices to apply the selection rules

        | Args:
        |    atoms (Optional[soprano.Atoms]): atoms object to gather lattice
        |                                     and spacegroup information from 
        |    latt_abc (Optional[np.ndarray]): periodic lattice in ABC form,
        |                                     Angstroms and radians
        |   n (Optional[int]): International number of the required spacegroup
        |   o (Optional[int]): Sub-option of the required spacegroup

        | Returns:
        |    xpeaks (XraySpectrum): a named tuple containing the peaks
        |                           with theta2, corresponding hkl indices,
        |                           a unique hkl tuple for each peak,
        |                           inverse reciprocal lattice distances,
        |                           intensities and wavelength

        | Raises:
        |   ValueError: if some of the arguments are invalid

        """

        # First a sanity check
        if [atoms, latt_abc].count(None) != 1:
            raise ValueError("""One and only one between atoms and latt_abc
                                must be passed to powder_peaks""")
        if atoms is not None:
            # Define the lattice
            latt_abc = utils.cart2abc(atoms.get_cell())
            # And the symmetry
            symm_data = spglib.get_symmetry_dataset(atoms)
            h = int(symm_data['hall_number'])
            try:
                sel_rule = xrdsel.get_sel_rule_from_hall(h)
            except ValueError:
                # Not found?
                raise RuntimeWarning("""Required symmetry not found - 
                                        No selection rules will be applied to
                                        XRD powder spectrum""")
        else:
            latt_abc = np.array(latt_abc, copy=False)
            if latt_abc.shape != (2, 3):
                raise ValueError(
                    "Invalid argument latt_abc passed to xrd_pwd_peaks")
            try:
                sel_rule = xrdsel.get_sel_rule_from_international(n, o)
            except ValueError:
                # Not found?
                raise RuntimeWarning("""Required symmetry not found - 
                                        No selection rules will be applied to
                                        XRD powder spectrum""")

        inv_d_max = 2.0/self.lambdax  # Upper limit to the inverse distance

        # Second, find the matrix linking hkl indices to the inverse distance
        hkl2d2 = utils.hkl2d2_matgen(latt_abc)
        hkl_bounds = utils.minimum_supcell(inv_d_max, r_matrix=hkl2d2)

        hrange = range(-hkl_bounds[0], hkl_bounds[0]+1)
        krange = range(-hkl_bounds[1], hkl_bounds[1]+1)
        lrange = range(-hkl_bounds[2], hkl_bounds[2]+1)

        # We now build a full grid of hkl indices. In this way
        # iteration is performed over numpy arrays and thus faster
        hkl_grid = np.array(
            np.meshgrid(hrange, krange, lrange)).reshape((3, -1))
        inv_d_grid = np.sqrt(np.sum(hkl_grid *
                                    np.tensordot(hkl2d2, hkl_grid,
                                                 axes=((1,), (0,))), axis=0))

        # Some will still have inv_d > inv_d_max, we fix that here
        # We also eliminate both 2theta = 0 and 2theta = pi to avoid
        # divergence later in the geometric factor
        valid_i = np.where((inv_d_grid < inv_d_max)*(inv_d_grid > 0))[0]
        hkl_grid = hkl_grid[:, valid_i]
        inv_d_grid = inv_d_grid[valid_i]
        # Now applying the selection rule
        selected_i = np.where(np.apply_along_axis(sel_rule, 0, hkl_grid))[0]
        hkl_grid = hkl_grid[:, selected_i]
        inv_d_grid = inv_d_grid[selected_i]
        theta_grid = np.arcsin(inv_d_grid/inv_d_max)
        # Now we calculate theta2.
        # Theta needs to be truncated to a certain number of
        # digits to avoid the same peak to be wrongly
        # considered as two.
        # This function also takes care of the sorting
        unique_sorting = np.unique(np.round(2.0*theta_grid*180.0/np.pi,
                                            self.theta2_digits),
                                   return_index=True,
                                   return_inverse=True)

        peak_n = len(unique_sorting[0])
        hkl_sorted = [hkl_grid[:,
                               np.where(unique_sorting[2] == i)[0]].T.tolist()
                      for i in range(peak_n)]
        hkl_unique = hkl_grid[:, unique_sorting[1]].T
        invd = inv_d_grid[unique_sorting[1]]
        xpeaks = XraySpectrum(unique_sorting[0],
                              np.array(hkl_sorted),
                              hkl_unique,
                              invd,
                              np.zeros(peak_n),
                              self.lambdax)

        return xpeaks


def xrd_spec_simul(xpeaks, th2_axis, peak_func=None,
                   peak_f_args=None, baseline=0.0):
    """
    Simulate an XRD spectrum given positions of peaks, intensities, baseline,
    and a peak function (a Gaussian by default).

    | Args:
    |   xpeaks (XraySpectrum): object containing the details of the XRD peaks
    |   th2_axis (np.ndarray): theta2 axis points on which the
    |                          spectrum should be simulated
    |   peak_func (Optional[function<float, float, *kargs>
    |                       => <np.ndarray>]): the function used to simulate
    |                                          peaks. Should take th2 as its
    |                                          first argument, peak centre as
    |                                          its second, and any number of
    |                                          optional arguments. Returns a
    |                                          numpy array containing the peak
    |                                          shape. Should be able to work
    |                                          with numpy arrays as input
    |   peak_f_args (Optional[list<float>]): optional arguments for peak_func.
    |                                        If no peak_func has been supplied
    |                                        by the user, the first value will
    |                                        be used as the Gaussian width
    |   baseline (Optional[float]): baseline to use as starting point for the
    |                               simulated spectrum

    | Returns:
    |   simul_spec (XraySpectrumData): simulated XRD spectrum
    |   simul_peaks (np.ndarray): simulated spectrum intensities broken by peak
    |                             contribution along axis 1

    | Raises:
    |   ValueError: if some of the arguments are invalid

    """

    # Sanity checks here

    peaks_th2 = np.array(xpeaks.theta2, copy=False)
    peaks_int = np.array(xpeaks.intensity, copy=False)
    th2_axis = np.array(th2_axis, copy=False)
    if len(th2_axis.shape) != 1:
        raise ValueError("Invalid th2_axis passed to xrd_spec_simul")

    # For peak_func there's little we can do to check, user's responsibility.
    if peak_func is not None:
        if len(inspect.getargspec(peak_func).args) > (2 + len(peak_f_args)):
            raise ValueError("Invalid peak_func passed to xrd_spec_simul")
    else:
        # A gaussian here
        peak_func = _gauss_peak_default
        if peak_f_args is None:
            # Use default width
            peak_f_args = [0.1]
        else:
            peak_f_args = peak_f_args[:1]

    # So here we are. Actual simulation!
    simul_peaks = peaks_int[None, :]*peak_func(th2_axis[:, None],
                                               peaks_th2[None, :],
                                               *peak_f_args)

    simul_spec = np.sum(simul_peaks, axis=1) + np.ones(len(th2_axis))*baseline
    simul_spec = XraySpectrumData(th2_axis, simul_spec)

    return simul_spec, simul_peaks


def xrd_exp_dataset(th2_axis, int_axis):
    """Build an experimental dataset as an XraySpectrumData object.

    | Args:
    |   th2_axis (np.ndarray): array containing the values for 2*theta
    |   int_axis (np.ndarray): array containing the values for intensity

    | Returns:
    |   exp_spec (XraySpectrumData): named tuple containing the experimental
    |                                dataset
    """

    # Sanity checks as usual
    th2_axis = np.array(th2_axis, copy=False)
    int_axis = np.array(int_axis, copy=False)

    if th2_axis.shape != int_axis.shape or len(th2_axis.shape) != 1:
        raise ValueError("Invalid dataset passed to xrd_exp_dataset")

    return XraySpectrumData(th2_axis, int_axis)


def xrd_leBail_Ifit(xpeaks, exp_spec,
                    peak_func=None, peak_f_args=[], baseline=0.0,
                    rwp_tol=1e-2, max_iter=100):
    """
    Perform a refining on an XraySpectrum object's intensities based on
    experimental data with leBail's method.

    | Args:
    |   xpeaks (XraySpectrum): object containing the details of the XRD peaks
    |   exp_spec (XraySpectrumData): experimental data, dataset built using
    |                                xrd_exp_dataset
    |   peak_func (Optional[function<float, float, *kargs>
    |                       => <np.ndarray>]): the function used to simulate
    |                                          peaks. Should take th2 as its
    |                                          first argument, peak centre as
    |                                          its second, and any number of
    |                                          optional arguments. Returns a
    |                                          numpy array containing the peak
    |                                          shape. Should be able to work
    |                                          with numpy arrays as input
    |   peak_f_args (Optional[list<float>]): optional arguments for peak_func.
    |                                        If no peak_func has been supplied
    |                                        by the user, the first value will
    |                                        be used as the Gaussian width
    |   baseline (Optional[float]): baseline of experimental data, if present
    |   rwp_tol (Optional[float]): tolerance on the Rwp error value between
    |                              two iterations that stops the calculation.
    |                              Default is 1e-2
    |   max_iter (Optional[int]): maximum number of iterations to perform

    | Returns:
    |   xpeaks_scaled (XraySpectrum): a new XraySpectrum object, with
    |                                 intensities properly scaled to match the
    |                                 experimental data
    |   simul_spec (np.ndarray): final simulated XRD spectrum
    |   simul_peaks (np.ndarray): final simulated spectrum broken by peak
    |                             contribution along axis 1
    |   rwp (float): the final value of Rwp (fitness of simulated to
    |                experimental data)

    | Raises:
    |   ValueError: if some of the arguments are invalid

    """

    # Sanity check (the rest is up to the other functions)
    if type(xpeaks) != XraySpectrum:
        raise ValueError("Invalid xpeaks passed to leBail_Ifit")
    if type(exp_spec) != XraySpectrumData:
        raise ValueError("Invalid exp_spec passed to leBail_Ifit")

    # Copy xpeaks so that the original object will stay unaltered
    xpeaks = copy.deepcopy(xpeaks)

    # Fetch the data
    peaks_th2 = xpeaks.theta2
    th2_axis = np.array(exp_spec.theta2, copy=False)
    int_axis = np.array(exp_spec.intensity, copy=False)
    # Find a suitable starting height for the peaks
    peaks_int = (xpeaks.intensity*0.0)+np.amax(int_axis)/4.0

    # Perform the first simulation
    simul_spec, simul_peaks = xrd_spec_simul(xpeaks, th2_axis,
                                             peak_func=peak_func,
                                             peak_f_args=peak_f_args,
                                             baseline=baseline)
    # Calculate Rwp
    rwp0 = _Rwp_eval(simul_spec.intensity, int_axis)

    # Now the iterations
    for i in range(max_iter):
        # Perform a correction
        peaks_int *= _leBail_rescale_I(simul_peaks, simul_spec.intensity,
                                       int_axis)
        # Store
        np.copyto(xpeaks.intensity, peaks_int)
        # Recalculate
        simul_spec, simul_peaks = xrd_spec_simul(xpeaks, th2_axis,
                                                 peak_func=peak_func,
                                                 peak_f_args=peak_f_args,
                                                 baseline=baseline)
        # Calculate Rwp
        rwp = _Rwp_eval(simul_spec.intensity, int_axis)
        # Gain?
        delta_rwp = abs((rwp-rwp0)/rwp)
        if delta_rwp < rwp_tol:
            break
        rwp0 = rwp

    return xpeaks, simul_spec, simul_peaks, rwp


# Here be utility functions that are NOT meant to be used by the uninitiated.
# Tread at your own peril.


def _Rwp_eval(simul_int, exp_int):
    """Evaluate Rwp for use in LeBail fitting"""

    weights = 1.0/exp_int

    r_wp = np.sqrt(np.sum(weights*(exp_int-simul_int)**2.0) /
                   np.sum(weights*exp_int**2.0))

    return r_wp


def _leBail_rescale_I(simul_peaks, simul_spec, exp_spec):
    """Returns rescaling factors for intensities in leBail fitting"""

    sum_peaks = np.sum(simul_peaks, axis=0)
    # It could be zero somewhere, fix that
    sum_peaks = np.where(sum_peaks > 0, sum_peaks, np.inf)
    i_scale = np.sum(exp_spec[:, None]*simul_peaks/simul_spec[:, None],
                     axis=0)/sum_peaks

    return i_scale


def _gauss_peak_default(x, x0, w):
    """Gaussian peak function (for spectrum simulation)"""
    return np.exp(-((x-x0)/w)**2.0)
