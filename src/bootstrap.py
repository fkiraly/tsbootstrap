from __future__ import annotations
from scipy.stats import poisson, expon, norm, gamma, beta, lognorm, weibull_min, pareto, geom, uniform
import inspect
from functools import partial
from scipy.signal.windows import tukey
from scipy.stats import rv_continuous
from fracdiff.sklearn import Fracdiff, FracdiffStat
from typing import Callable, List, Optional, Tuple, Union, Iterator
from sklearn.decomposition import PCA

from statsmodels.tsa.ar_model import AutoReg
import numpy as np
import pandas as pd
from abc import ABCMeta, abstractmethod
from numpy.random import Generator
from numbers import Integral

from utils.block_length_sampler import BlockLengthSampler
from src.block_resampler import BlockResampler
from src.block_generator import BlockGenerator
from utils.tsfit import *
from utils.tsmodels import *
from src.bootstrap_numba import *
from utils.odds_and_ends import check_generator, time_series_split

# TODO: add a check if generated block is only one unit long
# TODO: ensure docstrings align with functionality
# TODO: test -- check len(returned_indices) == X.shape[0]
# TODO: ensure x is 2d only for var, otherwise 1d or 2d with 1 feature


class BaseTimeSeriesBootstrap(metaclass=ABCMeta):
    """
    Base class for time series bootstrapping.
    """

    def __init__(self,  n_bootstraps: int = 10,
                 rng: Optional[Union[Generator, int]] = None) -> None:
        """
        Parameters
        ----------
        n_bootstraps : int, default=10
            The number of bootstrap samples to create.
        rng : int or Generator, default=np.random.default_rng()
            The random number generator or seed used to generate the bootstrap samples.
        """
        self.n_bootstraps = n_bootstraps
        self.rng = rng

    @property
    def rng(self):
        return self._rng

    @rng.setter
    def rng(self, value: Optional[Union[Generator, int]]) -> None:
        if value is None:
            value = np.random.default_rng()  # default random number generator
        elif not isinstance(value, (Generator, Integral)):
            raise TypeError(
                'The random number generator must be an instance of the numpy.random.Generator class, or an integer.')
        self._rng = check_generator(value)

    @property
    def n_bootstraps(self):
        return self._n_bootstraps

    @n_bootstraps.setter
    def n_bootstraps(self, value):
        if not isinstance(value, Integral):
            raise TypeError(
                'The number of bootstrap iterations must be an integer.')
        if not value > 0:
            raise ValueError(
                'The number of bootstrap iterations must be greater than 0.')
        self._n_bootstraps = value

    def split(self, X: Union[np.ndarray, pd.DataFrame, List], return_indices: bool = False, exog: Optional[np.ndarray] = None) -> Iterator[np.ndarray] | Iterator[Tuple[List[np.ndarray], np.ndarray]]:
        """Generate indices to split data into training and test set."""
        X = np.asarray(X)
        if len(X.shape) < 2:
            X = np.expand_dims(X, 1)

        self._check_input(X)

        X_train, X_test = time_series_split(
            X, test_ratio=0.2)
        if exog is not None:
            self._check_input(exog)
            exog_train, exog_test = time_series_split(
                exog, test_ratio=0.2)
        else:
            exog_train = None
            exog_test = None

        samples_iter = self._generate_samples(
            X=X_train, return_indices=return_indices, exog=exog_train)

        for train_samples in samples_iter:
            yield train_samples

    def _generate_samples(self, X: np.ndarray, return_indices: bool = False, exog: Optional[np.ndarray] = None) -> Iterator[np.ndarray]:
        """Generates bootstrapped samples directly.
        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            The input samples.

        Yields
        ------
        Iterator[np.ndarray]
            An iterator over the bootstrapped samples.

        """
        for _ in range(self.n_bootstraps):
            indices, data = self._generate_samples_single_bootstrap(
                X=X, exog=exog)
            data = np.concatenate(data, axis=0)
            if return_indices:
                yield indices, data
            else:
                yield data

    @abstractmethod
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Generates list of bootstrapped indices and samples for a single bootstrap iteration.
        Should be implemented in derived classes.
        """

    def _check_input(self, X):
        if np.any(np.diff([len(x) for x in X]) != 0):
            raise ValueError("All time series must be of the same length.")

    def get_n_splits(self, X: Optional[np.ndarray] = None, y: Optional[np.ndarray] = None,
                     groups: Optional[np.ndarray] = None) -> int:
        """Returns the number of bootstrapping iterations."""
        return self.n_bootstraps


class BlockBootstrap(BaseTimeSeriesBootstrap):
    """
    Block Bootstrap base class for time series data.

    Parameters
    ----------
    block_length : int, default=None
        The length of the blocks to sample. If None, the block length is automatically set to the square root of the number of observations.

    Raises
    ------
    ValueError
        If block_length is not greater than 0.
    """

    def __init__(self, n_bootstraps: int = 10, block_length: Optional[int] = None, block_length_distribution: Optional[str] = None, wrap_around_flag: bool = False, overlap_flag: bool = False, combine_generation_and_sampling_flag: bool = False, rng: Optional[Union[int, Generator]] = None, **kwargs) -> None:
        """
        Parameters
        ----------
        block_length : int or None, default=None
            The length of the blocks to sample. If None, the block length is automatically set to the square root of the number of observations.
        block_length_distribution : str or None, default=None
            The block length distribution function to use. If None, the block length distribution is automatically set to None (internally converted to "none" in BlockLengthSampler).
        wrap_around_flag : bool, default=False
            Whether to wrap around the input data when generating blocks.
        overlap_flag : bool, default=False
            Whether to allow blocks to overlap.
        combine_generation_and_sampling : bool, default=False

        Additional Parameters
        -----
        overlap_length : int or None
            The length of the overlap between blocks. Defaults to 1.
        min_block_length : int or None
            The minimum block length. Defaults to 1.
        block_weights : array-like of shape (X.shape[0],), or Callable, or None
            The weights with which to sample blocks, where block_weights[i] is the weight assigned to the ith block. Defaults to None.
        tapered_weights : array-like of shape (n_blocks,), or Callable, or None
            The tapered weights to assign to each block. Defaults to None.

        BlockLengthSampler Parameters
        -----
        block_length : int or None
        block_length_distribution : str or None

        BlockGenerator Parameters
        -----
        wrap_around_flag : bool, default=False
        overlap_flag : bool, default=False
        overlap_length : int or None
        min_block_length : int or None

        BlockResampler Parameters
        -----
        blocks : list of arrays
        block_weights : array-like of shape (X.shape[0],), or Callable, or None
        tapered_weights : array-like of shape (n_blocks,), or Callable, or None

        Common Parameters
        -----
        X : array-like of shape (n_samples, n_features)
        rng : int or Generator, default=None
        """

        super().__init__(n_bootstraps=n_bootstraps, rng=rng)
        self.block_length_distribution = block_length_distribution
        self.block_length = block_length
        self.wrap_around_flag = wrap_around_flag
        self.overlap_flag = overlap_flag
        self.combine_generation_and_sampling_flag = combine_generation_and_sampling_flag

        self.block_weights = kwargs.get("block_weights", None)
        self.tapered_weights = kwargs.get("tapered_weights", None)
        self.overlap_length = kwargs.get('overlap_length', None)
        self.min_block_length = kwargs.get('min_block_length', None)

        self.blocks = None
        self.block_resampler = None

    @property
    def block_length(self) -> Optional[int]:
        """Getter for block_length."""
        return self._block_length

    @block_length.setter
    def block_length(self, value) -> None:
        """
        Setter for block_length. Performs validation on assignment.
        Parameters
        ----------
        value : int or None
        """
        if value is not None:
            if not isinstance(value, Integral) or value < 1:
                raise ValueError(
                    "Block length needs to be None or an integer >= 1.")
        self._block_length = value

    @property
    def block_length_distribution(self) -> Optional[str]:
        """Getter for block_length_distribution."""
        return self._block_length_distribution

    @block_length_distribution.setter
    def block_length_distribution(self, value) -> None:
        """
        Setter for block_length_distribution. Performs validation on assignment.
        Parameters
        ----------
        value : str
            The block length distribution function to use.
        """
        if value is not None and not isinstance(value, str):
            raise ValueError("block_length_distribution must be a string.")
        self._block_length_distribution = value

    def _check_input(self, X: np.ndarray) -> None:
        super()._check_input(X)
        if self.block_length is not None and self.block_length > X.shape[0]:
            raise ValueError(
                "block_length cannot be greater than the size of the input array X.")

    def _generate_blocks(self, X: np.ndarray) -> List[np.ndarray]:
        """Generates blocks of indices.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        blocks : list of arrays
            The generated blocks.

        """

        block_length_sampler = BlockLengthSampler(
            avg_block_length=self.block_length if self.block_length is not None else int(
                np.sqrt(X.shape[0])),
            block_length_distribution=self.block_length_distribution,
            rng=self.rng)

        block_generator = BlockGenerator(
            block_length_sampler=block_length_sampler, input_length=X.shape[0], rng=self.rng, wrap_around_flag=self.wrap_around_flag, overlap_length=self.overlap_length, min_block_length=self.min_block_length)

        blocks = block_generator.generate_blocks(
            overlap_flag=self.overlap_flag)

        return blocks

    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Generate a single bootstrap sample.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        Tuple[List[np.ndarray], List[np.ndarray]]
            A tuple containing the indices and data of the generated blocks.
        """

        if self.combine_generation_and_sampling_flag or self.blocks is None:
            blocks = self._generate_blocks(X=X)

            block_resampler = BlockResampler(
                X=X,
                blocks=blocks,
                rng=self.rng,
                block_weights=self.block_weights,
                tapered_weights=self.tapered_weights
            )
        else:
            blocks = self.blocks
            block_resampler = self.block_resampler

        block_indices, block_data = block_resampler.resample_block_indices_and_data()

        if not self.combine_generation_and_sampling_flag:
            self.blocks = blocks
            self.block_resampler = block_resampler

        return block_indices, block_data


class MovingBlockBootstrap(BlockBootstrap):
    """
    Moving Block Bootstrap class for time series data.

    This class functions similarly to the base `BlockBootstrap` class, with
    the following modifications to the default behavior:
    * `overlap_flag` is always set to True, meaning that blocks can overlap.
    * `wrap_around_flag` is always set to False, meaning that the data will not
      wrap around when generating blocks.
    * `block_length_distribution` is always None, meaning that the block length
      distribution is not utilized.
    * `combine_generation_and_sampling_flag` is always False, meaning that the block
      generation and resampling are performed separately.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.overlap_flag = True
        self.wrap_around_flag = False
        self.block_length_distribution = None


class StationaryBlockBootstrap(BlockBootstrap):
    """
    Stationary Block Bootstrap class for time series data.

    This class functions similarly to the base `BlockBootstrap` class, with
    the following modifications to the default behavior:
    * `overlap_flag` is always set to True, meaning that blocks can overlap.
    * `wrap_around_flag` is always set to False, meaning that the data will not
        wrap around when generating blocks.
    * `block_length_distribution` is always "geometric", meaning that the block
        length distribution is geometrically distributed.
    * `combine_generation_and_sampling_flag` is always False, meaning that the block
        generation and resampling are performed separately.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.overlap_flag = True
        self.wrap_around_flag = False
        self.block_length_distribution = "geometric"


class CircularBlockBootstrap(BlockBootstrap):
    """
    Circular Block Bootstrap class for time series data.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.overlap_flag = True
        self.wrap_around_flag = True
        self.block_length_distribution = None


class NonOverlappingBlockBootstrap(BlockBootstrap):
    """
    Non-Overlapping Block Bootstrap class for time series data.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.overlap_flag = False
        self.wrap_around_flag = False
        self.block_length_distribution = None


class BaseBlockBootstrap(BlockBootstrap):
    bootstrap_type_dict = {
        'nonoverlapping': NonOverlappingBlockBootstrap,
        'moving': MovingBlockBootstrap,
        'stationary': StationaryBlockBootstrap,
        'circular': CircularBlockBootstrap
    }

    def __init__(self, bootstrap_type: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.bootstrap_instance: Optional[Union[NonOverlappingBlockBootstrap,
                                                MovingBlockBootstrap, StationaryBlockBootstrap, CircularBlockBootstrap]] = None
        if bootstrap_type is not None:
            if bootstrap_type not in self.bootstrap_type_dict:
                raise ValueError(
                    "bootstrap_type should be one of {}".format(list(self.bootstrap_type_dict.keys())))
            self.bootstrap_instance = self.bootstrap_type_dict[bootstrap_type](
                **kwargs)

    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        if self.bootstrap_instance is None:
            # Generate samples using the base BlockBootstrap method
            block_indices, block_data = super()._generate_samples_single_bootstrap(X=X, exog=exog)
        else:
            # Generate samples using the specified bootstrap_type
            if hasattr(self.bootstrap_instance, '_generate_samples_single_bootstrap'):
                block_indices, block_data = self.bootstrap_instance._generate_samples_single_bootstrap(
                    X=X, exog=exog)
            else:
                raise NotImplementedError(
                    f"The bootstrap class '{type(self.bootstrap_instance).__name__}' does not implement '_generate_samples_single_bootstrap' method.")

        return block_indices, block_data


'''
# TODO: add a method to set the block length. i.e. flesh out error_function.
class AdaptiveBlockLengthBootstrap(BaseBlockBootstrap):
    def __init__(self,
                 block_length_bins: List[int],
                 error_function: Callable,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.block_length_bins = block_length_bins
        self.error_function = error_function
        self._block_length = None

    @property
    def block_length(self) -> int:
        if self._block_length is None:
            raise ValueError(
                "block_length has not been set yet. Call the 'set_block_length' method with the data array.")
        return self._block_length

    def set_block_length(self, X: np.ndarray) -> None:
        errors = [self.error_function(block_length, X)
                  for block_length in self.block_length_bins]
        self._block_length = self.block_length_bins[np.argmin(errors)]
    
'''


# Be cautious when using the default windowing functions from numpy, as they drop to 0 at the edges.This could be particularly problematic for smaller block_lenghts. In the current implementation, we have clipped the min to 0.1, in block_resampler.py.

class BartlettsBootstrap(BaseBlockBootstrap):
    def __init__(self, *args, **kwargs):
        super().__init__(tapered_weights=np.bartlett,
                         bootstrap_type='moving', *args, **kwargs)


class HammingBootstrap(BaseBlockBootstrap):
    def __init__(self, *args, **kwargs):
        super().__init__(tapered_weights=np.hamming,
                         bootstrap_type='moving', *args, **kwargs)


class HanningBootstrap(BaseBlockBootstrap):
    def __init__(self, *args, **kwargs):
        super().__init__(tapered_weights=np.hanning,
                         bootstrap_type='moving', *args, **kwargs)


class BlackmanBootstrap(BaseBlockBootstrap):
    def __init__(self, *args, **kwargs):
        super().__init__(tapered_weights=np.blackman,
                         bootstrap_type='moving', *args, **kwargs)


class TukeyBootstrap(BaseBlockBootstrap):
    tukey_alpha = staticmethod(partial(tukey, alpha=0.5))

    def __init__(self, *args, **kwargs):
        super().__init__(tapered_weights=self.tukey_alpha,
                         bootstrap_type='moving', *args, **kwargs)


class BaseResidualBootstrap(BaseTimeSeriesBootstrap):
    def __init__(self, model_type: Literal["ar", "arima", "sarima", "var"] = "ar", order: Optional[Union[int, List[int], Tuple[int, int, int], Tuple[int, int, int, int]]] = None, save_models: bool = False, **kwargs):
        """
        order is a tuple of (p, o, q) for ARIMA and (p, d, q, s) for SARIMAX. It is either a single int or a list of non-consecutive ints for AR, and an int for VAR and ARCH. If None, the best order is chosen via TSFitBestLag. Do note that TSFitBestLag only chooses the best lag, not the best order, so for the tuple values, it only chooses the best p, not the best (p, o, q) or (p, d, q, s). The rest of the values are set to 0.
        """
        super().__init__(**kwargs)
        self.model_type = model_type
        self.order = order
        self.save_models = save_models

        self.fit_model = None
        self.resids = None
        self.X_fitted = None
        self.coefs = None

    @property
    def model_type(self) -> Literal["ar", "arima", "sarima", "var"]:
        return self._model_type

    @model_type.setter
    def model_type(self, value: Literal["ar", "arima", "sarima", "var"]) -> None:
        if not isinstance(value, str):
            raise TypeError(
                "model_type must be a string.")
        value = value.lower()
        if value not in ["ar", "arima", "sarima", "var"]:
            raise ValueError(
                "model_type must be one of 'ar', 'arima', 'sarima', or 'var'.")
        self._model_type = value

    @property
    def order(self) -> Optional[Union[int, List[int], Tuple[int, int, int], Tuple[int, int, int, int]]]:
        return self._order

    @order.setter
    def order(self, value) -> None:
        if value is not None:
            if not isinstance(value, Integral) and not isinstance(value, list) and not isinstance(value, tuple):
                raise TypeError(
                    "order must be an int, list, or tuple.")
            if isinstance(value, Integral) and value < 0:
                raise ValueError(
                    "order must be a positive integer.")
            if isinstance(value, list) and not all(isinstance(v, Integral) for v in value) and not all(v > 0 for v in value):
                raise TypeError(
                    "order must be a list of positive integers.")
            if isinstance(value, tuple) and not all(isinstance(v, Integral) for v in value) and not all(v > 0 for v in value):
                raise TypeError(
                    "order must be a tuple of positive integers.")
        self._order = value

    def _fit_model(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> None:
        if self.resids is None or self.X_fitted is None or self.fit_model is None or self.coefs is None:
            fit_obj = TSFitBestLag(model_type=self.model_type, order=self.order,
                                   save_models=self.save_models)
            self.fit_model = fit_obj.fit(X=X, exog=exog).model
            self.X_fitted = fit_obj.get_fitted_X()
            self.resids = fit_obj.get_residuals()
            self.order = fit_obj.get_order()
            self.coefs = fit_obj.get_coefs()


# Fit, then resample residuals.
class WholeResidualBootstrap(BaseResidualBootstrap):

    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        self._fit_model(X=X, exog=exog)

        # Resample residuals
        resampled_indices = generate_random_indices(
            self.resids.shape[0], self.rng)
        resampled_residuals = self.resids[resampled_indices]
        # Add the bootstrapped residuals to the fitted values
        bootstrap_samples = self.X_fitted + resampled_residuals
        return [resampled_indices], [bootstrap_samples]


class BlockResidualBootstrap(BaseResidualBootstrap, BaseBlockBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        BaseResidualBootstrap._fit_model(
            self, X=X, exog=exog)
        block_indices, block_data = BaseBlockBootstrap._generate_samples_single_bootstrap(
            self, X=self.resids)

        # Add the bootstrapped residuals to the fitted values
        bootstrap_samples = self.X_fitted + np.concatenate(block_data, axis=0)

        return block_indices, [bootstrap_samples]


# TODO: higher-order Markov models or conditional variants of HMMs (e.g., Input-Output HMMs or Factorial HMMs).
# TODO: logic might need some changing to incorporate genearted block_indices into `generate_samples_markov`
# TODO: test -- call sample before fit and see if it raises an error.
class BaseMarkovBootstrap(BaseTimeSeriesBootstrap):
    def __init__(self, method: str = "mean", apply_pca_flag: bool = False, pca: Optional[PCA] = None,
                 n_iter_hmm: int = 100, n_fits_hmm: int = 10, blocks_as_hidden_states_flag: bool = False, n_states: int = 5, *args, **kwargs):
        """
        Notes
        -----
        Fitting Markov models is expensive, hence we do not allow re-fititng. We instead fit once to the residuals and generate new samples by changing the random_seed.
        """
        super().__init__(*args, **kwargs)
        self.method = method
        self.apply_pca_flag = apply_pca_flag
        self.pca = pca
        self.n_iter_hmm = n_iter_hmm
        self.n_fits_hmm = n_fits_hmm
        self.blocks_as_hidden_states_flag = blocks_as_hidden_states_flag
        self.n_states = n_states

        self.hmm_object = None


# Fit HMM to residuals, then sample from the HMM with different random seeds.
class WholeMarkovBootstrap(BaseMarkovBootstrap, BaseResidualBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        BaseResidualBootstrap._fit_model(
            self, X=X, exog=exog)

        random_seed = self.rng.integers(0, 1000)
        if self.hmm_object is None:
            markov_sampler = MarkovSampler(apply_pca_flag=self.apply_pca_flag, pca=self.pca, n_iter_hmm=self.n_iter_hmm, n_fits_hmm=self.n_fits_hmm,
                                           method=self.method, blocks_as_hidden_states_flag=self.blocks_as_hidden_states_flag, random_seed=random_seed)

            markov_sampler.fit(
                blocks=self.resids, n_states=self.n_states)
            self.hmm_object = markov_sampler

        bootstrapped_resids = self.hmm_object.sample(
            random_seed=random_seed + self.rng.integers(0, 1000))[0]
        bootstrap_samples = self.X_fitted + bootstrapped_resids

        return [np.arange(X.shape[0])], [bootstrap_samples]


# Fit HMM to residuals, then resample using blocks once, then sample from the HMM with different random seeds.
class BlockMarkovBootstrap(BaseMarkovBootstrap, BaseResidualBootstrap, BaseBlockBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        BaseResidualBootstrap._fit_model(
            self, X=X, exog=exog)
        block_indices, block_data = BaseBlockBootstrap._generate_samples_single_bootstrap(
            self, X=self.resids)

        random_seed = self.rng.integers(0, 1000)
        if self.hmm_object is None:
            markov_sampler = MarkovSampler(apply_pca_flag=self.apply_pca_flag, pca=self.pca, n_iter_hmm=self.n_iter_hmm, n_fits_hmm=self.n_fits_hmm,
                                           method=self.method, blocks_as_hidden_states_flag=self.blocks_as_hidden_states_flag, random_seed=random_seed)

            markov_sampler.fit(
                blocks=block_data, n_states=self.n_states)
            self.hmm_object = markov_sampler

        # Add the bootstrapped residuals to the fitted values
        bootstrapped_resids = self.hmm_object.sample(
            random_seed=random_seed + self.rng.integers(0, 1000))[0]
        bootstrap_samples = self.X_fitted + bootstrapped_resids

        return block_indices, [bootstrap_samples]


# Preserve the statistic/bias in the original data.


# TODO: test -- see if the statistic on the bootstrapped sample is close to the statistic on the original sample.
class BaseBiasCorrectedBootstrap(BaseTimeSeriesBootstrap):
    """Bootstrap class that generates bootstrapped samples preserving a specific statistic.

    This class generates bootstrapped time series data, preserving a given statistic (such as mean, median, etc.)
    The statistic is calculated from the original data and then used as a parameter for generating the bootstrapped samples.

    Parameters
    ----------
    *args:
        Variable length argument list.
    statistic : Callable, default np.mean
        A callable function to compute the statistic that should be preserved. This function should take a numpy array as input,
        and return a scalar or a numpy array as output. For example, you can pass np.mean, np.median, or any other custom function.
    **kwargs:
        Arbitrary keyword arguments.

    Attributes
    ----------
    statistic_X : scalar or np.ndarray
        The value of the preserved statistic computed from the original data. It is None until `_generate_samples_single_bootstrap` is first called.

    """

    def __init__(self, *args, statistic: Callable = np.mean, statistic_axis: int = 0, statistic_keepdims: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.statistic = statistic
        self.statistic_axis = statistic_axis
        self.statistic_keepdims = statistic_keepdims

        self.statistic_X = None

    @property
    def statistic(self) -> Callable:
        """Get the current statistic function."""
        return self._statistic

    @statistic.setter
    def statistic(self, value: Callable) -> None:
        """Set a new statistic function.

        The new function must be callable. If it is not, a TypeError will be raised.
        """
        if not callable(value):
            raise TypeError("statistic must be a callable.")
        self._statistic = value

    def _calculate_statistic(self, X: np.ndarray) -> np.ndarray:
        params = inspect.signature(self.statistic).parameters
        kwargs_stat = {'axis': self.statistic_axis,
                       'keepdims': self.statistic_keepdims}
        kwargs_stat = {k: v for k, v in kwargs_stat.items() if k in params}
        statistic_X = self.statistic(X, **kwargs_stat)
        return statistic_X


class WholeBiasCorrectedBootstrap(BaseBiasCorrectedBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        if self.statistic_X is None:
            self.statistic_X = self._calculate_statistic(X=X)

        # Resample residuals
        resampled_indices = generate_random_indices(
            X.shape[0], self.rng)
        bootstrapped_sample = X[resampled_indices]
        # Calculate the bootstrapped statistic
        statistic_bootstrapped = self._calculate_statistic(bootstrapped_sample)
        # Calculate the bias
        bias = self.statistic_X - statistic_bootstrapped
        # Add the bias to the bootstrapped sample
        bootstrap_sample_bias_corrected = bootstrapped_sample + \
            bias.reshape(bootstrapped_sample.shape)
        return [resampled_indices], [bootstrap_sample_bias_corrected]


class BlockBiasCorrectedBootstrap(BaseBiasCorrectedBootstrap, BaseBlockBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        if self.statistic_X is None:
            self.statistic_X = BaseBiasCorrectedBootstrap._calculate_statistic(
                self, X=X)
        block_indices, block_data = BaseBlockBootstrap._generate_samples_single_bootstrap(
            self, X=X)

        block_data_concat = np.concatenate(block_data, axis=0)
        # Calculate the bootstrapped statistic
        statistic_bootstrapped = self._calculate_statistic(block_data_concat)
        # Calculate the bias
        bias = self.statistic_X - statistic_bootstrapped
        # Add the bias to the bootstrapped sample
        bootstrap_samples = block_data_concat + bias
        return block_indices, [bootstrap_samples]


class BaseDistributionBootstrap(BaseResidualBootstrap):
    """
    Implementation of the Distribution Bootstrap (DB) method for time series data.

    Parameters
    ----------
    distribution: str, default='normal'
        The distribution
    """
    distribution_methods = {
        "poisson": poisson,
        "exponential": expon,
        "normal": norm,
        "gamma": gamma,
        "beta": beta,
        "lognormal": lognorm,
        "weibull": weibull_min,
        "pareto": pareto,
        "geometric": geom,
        "uniform": uniform
    }

    def __init__(self, *args, distribution: str = 'normal', refit: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.distribution = distribution
        self.refit = refit

        self.resids_dist = None
        self.resids_dist_params = ()

    @property
    def distribution(self) -> str:
        """Getter for distribution."""
        return self._distribution

    @distribution.setter
    def distribution(self, value: str) -> None:
        """Setter for distribution. Performs validation on assignment."""
        if not isinstance(value, str):
            raise TypeError("distribution must be a string.")

        # Check if the distribution exists in the dictionary
        if value.lower() not in self.distribution_methods:
            raise ValueError(
                f"Invalid distribution: {value}; must be a valid distribution name in distribution_methods.")
        self._distribution = value.lower()

    def fit_distribution(self, resids: np.ndarray) -> Tuple[rv_continuous, Tuple]:
        # getattr(distributions, self.distribution)
        dist = self.distribution_methods[self.distribution]
        # Fit the distribution to the residuals
        params = dist.fit(resids)
        resids_dist = dist
        resids_dist_params = params
        return resids_dist, resids_dist_params


# Resample resids, then fit.
class WholeDistributionBootstrap(BaseDistributionBootstrap, BaseResidualBootstrap):

    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        # Fit the model and residuals
        BaseResidualBootstrap._fit_model(self, X=X, exog=exog)
        # Fit the specified distribution to the residuals
        if not self.refit:
            if self.resids_dist is None or self.resids_dist_params == ():
                self.resids_dist, self.resids_dist_params = BaseDistributionBootstrap.fit_distribution(
                    self, self.resids)

            # Generate new residuals from the fitted distribution
            bootstrap_residuals = self.resids_dist.rvs(
                size=X.shape[0], *self.resids_dist_params, random_state=self.rng.integers(0, 2**32-1)).reshape(-1, 1)

            # Add new residuals to the fitted values to create the bootstrap time series
            bootstrap_samples = self.X_fitted + bootstrap_residuals
            return [np.arange(0, X.shape[0])], [bootstrap_samples]

        else:
            # Resample residuals
            resampled_indices = generate_random_indices(
                self.resids.shape[0], self.rng)
            resampled_residuals = self.resids[resampled_indices]
            resids_dist, resids_dist_params = BaseDistributionBootstrap.fit_distribution(
                self, resampled_residuals)
            # Generate new residuals from the fitted distribution
            bootstrap_residuals = resids_dist.rvs(
                size=X.shape[0], *resids_dist_params, random_state=self.rng).reshape(-1, 1)

            # Add the bootstrapped residuals to the fitted values
            bootstrap_samples = self.X_fitted + resampled_residuals
            return [resampled_indices], [bootstrap_samples]


class BlockDistributionBootstrap(BaseDistributionBootstrap, BaseBlockBootstrap, BaseResidualBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        # Fit the model and residuals
        BaseResidualBootstrap._fit_model(self, X=X, exog=exog)
        block_indices, block_data = BaseBlockBootstrap._generate_samples_single_bootstrap(
            self, X=self.resids)
        block_data_concat = np.concatenate(block_data, axis=0)
        # Fit the specified distribution to the residuals
        if not self.refit:
            if self.resids_dist is None or self.resids_dist_params == ():
                self.resids_dist, self.resids_dist_params = BaseDistributionBootstrap.fit_distribution(
                    self, block_data_concat)

            # Generate new residuals from the fitted distribution
            bootstrap_residuals = self.resids_dist.rvs(
                size=X.shape[0], *self.resids_dist_params, random_state=self.rng.integers(0, 2**32-1)).reshape(-1, 1)

            # Add new residuals to the fitted values to create the bootstrap time series
            bootstrap_samples = self.X_fitted + bootstrap_residuals
            return [np.arange(0, X.shape[0])], [bootstrap_samples]

        else:
            # Resample residuals
            resids_dist, resids_dist_params = BaseDistributionBootstrap.fit_distribution(
                self, block_data_concat)
            # Generate new residuals from the fitted distribution
            bootstrap_residuals = resids_dist.rvs(
                size=X.shape[0], *resids_dist_params, random_state=self.rng).reshape(-1, 1)

            # Add the bootstrapped residuals to the fitted values
            bootstrap_samples = self.X_fitted + bootstrap_residuals
            return block_indices, [bootstrap_samples]


VALID_MODELS = [AutoReg, ARIMA, SARIMAX, VAR, arch_model]


class BaseSieveBootstrap(BaseResidualBootstrap):
    def __init__(self, resids_model_type: Literal["ar", "arima", "sarima", "var", "arch"] = "ar", resids_order: Optional[Union[int, List[int], Tuple[int, int, int], Tuple[int, int, int, int]]] = None, refit: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resids_model_type = resids_model_type
        self.resids_order = resids_order
        self.refit = refit

        self.resids_coefs = None
        self.resids_fit_model = None

    @property
    def resids_model_type(self) -> Literal["ar", "arima", "sarima", "var", "arch"]:
        return self._resids_model_type

    @resids_model_type.setter
    def resids_model_type(self, value: Literal["ar", "arima", "sarima", "var", "arch"]) -> None:
        if not isinstance(value, str):
            raise TypeError(
                "resids_model_type must be a string.")
        value = value.lower()
        if value not in ["ar", "arima", "sarima", "var"]:
            raise ValueError(
                "resids_model_type must be one of 'ar', 'arima', 'sarima', or 'var'.")
        self._resids_model_type = value

    @property
    def resids_order(self) -> Optional[Union[int, List[int], Tuple[int, int, int], Tuple[int, int, int, int]]]:
        return self._resids_order

    @resids_order.setter
    def resids_order(self, value) -> None:
        if value is not None:
            if not isinstance(value, Integral) and not isinstance(value, list) and not isinstance(value, tuple):
                raise TypeError(
                    "resids_order must be an int, list, or tuple.")
            if isinstance(value, Integral) and value < 0:
                raise ValueError(
                    "resids_order must be a positive integer.")
            if isinstance(value, list) and not all(isinstance(v, Integral) for v in value) and not all(v > 0 for v in value):
                raise TypeError(
                    "resids_order must be a list of positive integers.")
            if isinstance(value, tuple) and not all(isinstance(v, Integral) for v in value) and not all(v > 0 for v in value):
                raise TypeError(
                    "resids_order must be a tuple of positive integers.")
        self._resids_order = value

    def _fit_resids_model(self, X: np.ndarray) -> Tuple[VALID_MODELS, Union[int, List[int], Tuple[int, int, int], Tuple[int, int, int, int]], np.ndarray]:
        resids_fit_obj = TSFitBestLag(
            model_type=self.resids_model_type, order=self.resids_order, save_models=self.save_models)
        resids_fit_model = resids_fit_obj.fit(
            X, exog=None).model
        resids_order = resids_fit_obj.get_order()
        resids_coefs = resids_fit_obj.get_coefs()
        return resids_fit_model, resids_order, resids_coefs


class WholeSieveBootstrap(BaseSieveBootstrap, BaseResidualBootstrap):

    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:

        BaseResidualBootstrap._fit_model(self, X=X, exog=exog)

        if not self.refit:
            if self.resids_fit_model is None or self.resids_coefs is None:
                self.resids_fit_model, self.resids_order, self.resids_coefs = BaseSieveBootstrap._fit_resids_model(
                    self, self.resids)
                # print(f"self.resids shape: {self.resids.shape}")
                # print(f"self.resids_fit_model: {self.resids_fit_model}")
                print(f"self.resids_order: {self.resids_order}")
                # print(f"self.resids_coefs.shape: {self.resids_coefs.shape}")

            bootstrap_samples = generate_samples_sieve(
                X_fitted=self.X_fitted, model_type=self.resids_model_type, resids_lags=self.resids_order, resids_coefs=self.resids_coefs, resids=self.resids, resids_fit_model=self.resids_fit_model, rng=self.rng.integers(0, 2**32-1))

            return [np.arange(0, X.shape[0])], [bootstrap_samples]

        else:
            # Resample residuals
            resampled_indices = generate_random_indices(
                self.resids.shape[0], self.rng)
            resampled_residuals = self.resids[resampled_indices]
            # print(f"resampled_residuals shape: {resampled_residuals.shape}")
            resids_fit_model, resids_order, resids_coefs = BaseSieveBootstrap._fit_resids_model(
                self, resampled_residuals)
            # print(f"resids_fit_model: {resids_fit_model}")
            print(f"resids_order: {resids_order}")
            # print(f"resids_coefs.shape: {resids_coefs.shape}")

            bootstrap_samples = generate_samples_sieve(
                X_fitted=self.X_fitted, model_type=self.resids_model_type, resids_lags=resids_order, resids_coefs=resids_coefs, resids=resampled_residuals, resids_fit_model=resids_fit_model, rng=self.rng.integers(0, 2**32-1))

            return [resampled_indices], [bootstrap_samples]


'''

class BlockSieveBootstrap(BaseSieveBootstrap, BaseBlockBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, random_seed: Optional[int], **kwargs) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        block_indices, block_data = super()._generate_samples_single_bootstrap(X=X,
                                                                               random_seed=random_seed, **kwargs)

        bootstrap_samples = []

        for block_data_iter in enumerate(block_data):
            fit_obj = TSFitBestLag(model_type=self.model_type, order=self.order,
                                   save_models=kwargs.get('save_models', False))
            fit_obj.fit(X=block_data_iter, exog=kwargs.get('exog', None))
            X_fitted = fit_obj.get_fitted_X()
            resids = fit_obj.get_residuals()

            resids_fit_obj = TSFitBestLag(
                model_type=self.resids_model_type, order=self.resids_order, save_models=kwargs.get('save_models', False))
            resids_fit_model = resids_fit_obj.fit(resids, exog=None)
            resids_order = resids_fit_obj.get_order()
            resids_coefs = resids_fit_obj.get_coefs()

            bootstrap_samples_iter = generate_samples_sieve(
                X_fitted=X_fitted, random_seed=random_seed, model_type=self.resids_model_type, resids_lags=resids_order, resids_coefs=resids_coefs, resids=resids, resids_fit_model=resids_fit_model)
            bootstrap_samples.append(bootstrap_samples_iter)

        return block_indices, bootstrap_samples

'''


class BaseFractionalDifferencingBootstrap(BaseTimeSeriesBootstrap):
    """
    Implementation of the Fractional Differencing Bootstrap (FDB) method for time series data.

    Parameters
    ----------
    d: float, default=0.5
        The order of differencing to be applied on the time series before bootstrap sampling.
    """

    def __init__(self, *args, diff_order: Optional[float] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fracdiff_transformer = None
        self.diff_order = diff_order

        self.X_diff = None

    @property
    def diff_order(self):
        return self._diff_order

    @diff_order.setter
    def diff_order(self, value):
        if value is not None and (not isinstance(value, float) or value > 0.5):
            raise ValueError("diff_order must be a float <= 0.5")
        self._diff_order = value
        self._fracdiff_transformer = self._create_fracdiff_transformer()

    def _create_fracdiff_transformer(self):
        if self.diff_order is None:
            return FracdiffStat()
        else:
            return Fracdiff(self.diff_order)

    @property
    def fracdiff_transformer(self):
        return self._fracdiff_transformer

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fracdiff_transformer.fit_transform(X)


# Fit, then resample.
class WholeFractionalDifferencingBootstrap(BaseFractionalDifferencingBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Fractionally difference the series, perform standard bootstrap on the differenced series,
        then apply the inverse fractional differencing to get the bootstrap sample.
        """
        if self.X_diff is None:
            self.X_diff = self.fit_transform(X)

        # Resample residuals
        bootstrap_indices = generate_random_indices(
            self.X_diff.shape[0], self.rng)
        bootstrap_samples = self.X_diff[bootstrap_indices]
        return bootstrap_indices, [bootstrap_samples]


class BlockFractionalDifferencingBootstrap(BaseFractionalDifferencingBootstrap, BaseBlockBootstrap):
    def _generate_samples_single_bootstrap(self, X: np.ndarray, exog: Optional[np.ndarray] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:

        if self.X_diff is None:
            self.X_diff = BaseFractionalDifferencingBootstrap.fit_transform(
                self, X)

        block_indices, block_data = BaseBlockBootstrap._generate_samples_single_bootstrap(self,
                                                                                          X=self.X_diff)
        return block_indices, block_data
