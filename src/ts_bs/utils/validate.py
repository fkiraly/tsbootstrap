from numbers import Integral
from typing import Any, List, Optional, Tuple, Union, get_args

import numpy as np
from numpy import ndarray
from numpy.random import Generator
from sklearn.utils import check_array
from ts_bs.utils.odds_and_ends import check_generator
from ts_bs.utils.types import FittedModelType, RngTypes


def validate_integers(
    *values: Union[Integral, List[Integral], np.ndarray],
    min_value: Optional[Integral] = None,
) -> None:
    """
    Validates that all input values are integers and optionally, above a minimum value.

    Each value can be an integer, a list of integers, or a 1D numpy array of integers.
    If min_value is provided, all integers must be greater than or equal to min_value.

    Parameters
    ----------
    *values : Union[Integral, List[Integral], np.ndarray]
        One or more values to validate.
    min_value : Integral, optional
        If provided, all integers must be greater than or equal to min_value.

    Raises
    ------
    TypeError
        If a value is not an integer, list of integers, or 1D array of integers,
        or if any integer is less than min_value.

    """
    for value in values:
        if isinstance(value, Integral):
            # If value is an integer, check if it's at least min_value if required
            if min_value is not None and value < min_value:
                raise ValueError(
                    f"All integers must be at least {min_value}. Got {value}."
                )
            continue

        if isinstance(value, list):
            # Check if the list is empty
            if not value:
                raise TypeError(f"List must not be empty. Got {value}.")

            # Check if every element in the list is an integer
            if not all(isinstance(x, Integral) for x in value):
                raise TypeError(
                    f"All elements in the list must be integers. Got {value}."
                )

            # Check if every element in the list is at least min_value if required
            if min_value is not None and any(x < min_value for x in value):
                raise ValueError(
                    f"All integers in the list must be at least {min_value}. Got {value}."
                )
            continue

        if isinstance(value, np.ndarray):
            # Check if the array is empty
            if value.size == 0:
                raise TypeError(f"Array must not be empty. Got {value}.")

            # Check if the array is 1D and if every element is an integer
            # i for signed integer, u for unsigned integer
            if value.ndim != 1 or value.dtype.kind not in "iu":
                raise TypeError(
                    f"Array must be 1D and contain only integers. Got {value}."
                )

            # Check if every element in the array is at least min_value if required
            if min_value is not None and any(value < min_value):
                raise ValueError(
                    f"All integers in the array must be at least {min_value}. Got {value}."
                )
            continue

        # If none of the above conditions are met, the input is invalid
        raise TypeError(
            f"Input must be an integer, a list of integers, or a 1D array of integers. Got {value}."
        )


def validate_X_and_exog(
    X: ndarray,
    exog: Optional[np.ndarray],
    model_is_var: bool = False,
    model_is_arch: bool = False,
) -> Tuple[ndarray, Optional[np.ndarray]]:
    """
    Validate and reshape input data and exogenous variables.

    Parameters
    ----------
    X : ndarray
        The input data.
    exog : Optional[np.ndarray]
        The exogenous variables.
    model_is_var : bool, optional
        Whether the model is a VAR model. Default is False.
    model_is_arch : bool, optional
        Whether the model is an ARCH model. Default is False.

    Returns
    -------
        Tuple[ndarray, Optional[np.ndarray]]: The validated and reshaped X and exog arrays.
    """
    # Validate and reshape X
    # Check if X is a non-empty NumPy array
    if not isinstance(X, np.ndarray) or X.dtype.kind not in "iuf":
        raise TypeError("X must be a NumPy array of floats.")
    if X.size < 2:
        raise ValueError("X must contain at least two elements.")
    if not model_is_var:
        X = check_array(
            X,
            ensure_2d=False,
            force_all_finite=True,
            dtype=[np.float64, np.float32],
        )
        # X = np.squeeze(X)
        if X.ndim > 2 or (X.ndim == 2 and X.shape[1] != 1):
            raise ValueError(
                "X must be 1-dimensional or 2-dimensional with a single column"
            )
            # raise ValueError("X must be 1-dimensional")
        if X.ndim == 1:
            X = X[:, np.newaxis]
    else:
        X = check_array(
            X,
            ensure_2d=True,
            force_all_finite=True,
            dtype=[np.float64, np.float32],
        )
        if X.shape[1] < 2:
            raise ValueError("X must be 2-dimensional with at least 2 columns")

    # Validate and reshape exog if necessary
    if exog is not None:
        # Check if exog is a non-empty NumPy array
        if not isinstance(exog, np.ndarray) or exog.dtype.kind not in "iuf":
            raise TypeError("exog must be a NumPy array of floats.")
        if exog.size < 2:
            raise ValueError("exog must contain at least two elements.")
        if exog.ndim == 1:
            exog = exog[:, np.newaxis]
        exog = check_array(
            exog,
            ensure_2d=True,
            force_all_finite=True,
            dtype=[np.float64, np.float32],
        )
        if exog.shape[0] != X.shape[0]:  # type: ignore
            raise ValueError(
                "The number of rows in exog must be equal to the number of rows in X."
            )

    # Ensure contiguous arrays for ARCH models
    if model_is_arch:
        X = np.ascontiguousarray(X)
        if exog is not None:
            exog = np.ascontiguousarray(exog)

    return X, exog


def validate_block_indices(
    block_indices: List[np.ndarray], input_length: Integral
) -> None:
    """
    Validate the input block indices. Each block index must be a 1D NumPy array with at least one index and all indices must be within the range of X.

    Parameters
    ----------
    block_indices : List[np.ndarray]
        The input block indices.
    input_length : Integral
        The length of the input data.

    Raises
    ------
    TypeError
        If block_indices is not a list or if it contains non-NumPy arrays.
    ValueError
        If block_indices is empty or if it contains NumPy arrays with non-integer values,
        or if it contains NumPy arrays with no indices, or if it contains NumPy arrays
        with indices outside the range of X.
    """
    # Check if 'block_indices' is a list
    if not isinstance(block_indices, list):
        raise TypeError("Input 'block_indices' must be a list.")

    # Check if 'block_indices' is empty
    if len(block_indices) == 0:
        raise ValueError("Input 'block_indices' must not be empty.")

    # Check if 'block_indices' contains only NumPy arrays
    if not all(isinstance(block, np.ndarray) for block in block_indices):
        raise TypeError(
            "Input 'block_indices' must be a list of NumPy arrays."
        )

    # Check if 'block_indices' contains only 1D NumPy arrays with integer values
    if not all(
        block.ndim == 1 and np.issubdtype(block.dtype, np.integer)
        for block in block_indices
    ):
        raise ValueError(
            "Input 'block_indices' must be a list of 1D NumPy arrays with integer values."
        )

    # Check if 'block_indices' contains only NumPy arrays with at least one index
    if not all(block.size > 0 for block in block_indices):
        raise ValueError(
            "Input 'block_indices' must be a list of 1D NumPy arrays with at least one index."
        )

    # Check if 'block_indices' contains only NumPy arrays with indices within the range of X
    if not all(np.all(block < input_length) for block in block_indices):
        raise ValueError(
            "Input 'block_indices' must be a list of 1D NumPy arrays with indices within the range of X."
        )


def validate_blocks(blocks: List[np.ndarray]) -> None:
    """
    Validate the input blocks. Each block must be a 2D NumPy array with at least one element.

    Parameters
    ----------
    blocks : List[np.ndarray]
        The input blocks.

    Raises
    ------
    TypeError
        If blocks is not a list or if it contains non-NumPy arrays.
    ValueError
        If blocks is empty or if it contains NumPy arrays with non-finite values,
        or if it contains NumPy arrays with no elements, or if it contains NumPy arrays
        with no features, or if it contains NumPy arrays with different number of features.
    """
    # Check if 'blocks' is a list
    if not isinstance(blocks, list):
        raise TypeError("Input 'blocks' must be a list.")

    # Check if 'blocks' is empty
    if len(blocks) == 0:
        raise ValueError("Input 'blocks' must not be empty.")

    # Check if 'blocks' contains only NumPy arrays
    if not all(isinstance(block, np.ndarray) for block in blocks):
        raise TypeError("Input 'blocks' must be a list of NumPy arrays.")

    # Check if 'blocks' contains only 2D NumPy arrays
    if not all(block.ndim == 2 for block in blocks):
        raise ValueError("Input 'blocks' must be a list of 2D NumPy arrays.")

    # Check if 'blocks' contains only NumPy arrays with at least one element
    if not all(block.shape[0] > 0 for block in blocks):
        raise ValueError(
            "Input 'blocks' must be a list of 2D NumPy arrays with at least one element."
        )

    # Check if 'blocks' contains only NumPy arrays with at least one feature
    if not all(block.shape[1] > 0 for block in blocks):
        raise ValueError(
            "Input 'blocks' must be a list of 2D NumPy arrays with at least one feature."
        )

    # Check if 'blocks' contains only NumPy arrays with the same number of features
    if not all(block.shape[1] == blocks[0].shape[1] for block in blocks):
        raise ValueError(
            "Input 'blocks' must be a list of 2D NumPy arrays with the same number of features."
        )

    # Check if 'blocks' contains NumPy arrays with finite values
    if not all(np.all(np.isfinite(block)) for block in blocks):
        raise ValueError(
            "Input 'blocks' must be a list of 2D NumPy arrays with finite values."
        )


def validate_weights(weights: np.ndarray) -> None:
    """
    Validate the input weights. Each weight must be a non-negative finite value.

    Parameters
    ----------
    weights : np.ndarray
        The input weights.

    Raises
    ------
    TypeError
        If weights is not a NumPy array.
    ValueError
        If weights contains any non-finite values, or if it contains any negative values,
        or if it contains any complex values, or if it contains all zeros,
        or if it is a 2D array with more than one column.
    """
    # Check if weights contains any non-finite values
    if not np.isfinite(weights).all():
        raise ValueError(
            "The provided callable function or array resulted in non-finite values. Please check your inputs."
        )
    # Check if weights contains any negative values
    if np.any(weights < 0):
        raise ValueError(
            "The provided callable function resulted in negative values. Please check your function."
        )
    # Check if weights contains any complex values
    if np.any(np.iscomplex(weights)):
        raise ValueError(
            "The provided callable function resulted in complex values. Please check your function."
        )
    # Check if weights contains all zeros
    if np.all(weights == 0):
        raise ValueError(
            "The provided callable function resulted in all zero values. Please check your function."
        )
    # Check if tapered_weights_arr is a 1D array or a 2D array with a single column
    if (weights.ndim == 2 and weights.shape[1] != 1) or weights.ndim > 2:
        raise ValueError(
            "The provided callable function resulted in a 2D array with more than one column. Please check your function."
        )


def validate_fitted_model(fitted_model: FittedModelType) -> None:
    """
    Validate the input fitted model. It must be an instance of a fitted model class.

    Parameters
    ----------
    fitted_model : FittedModelType
        The input fitted model.

    Raises
    ------
    TypeError
        If fitted_model is not an instance of a fitted model class.
    """
    valid_types = FittedModelType.__args__  # type: ignore
    if not isinstance(fitted_model, valid_types):
        valid_names = ", ".join([t.__name__ for t in valid_types])
        raise TypeError(
            f"fitted_model must be an instance of {valid_names}. Got {type(fitted_model).__name__} instead."
        )


def validate_literal_type(input_value: str, literal_type: Any) -> None:
    """Validate the type of input_value against a Literal type.

    This function validates if the input_value is among the valid types defined
    in the literal_type.

    Parameters
    ----------
    input_value : str
        The value to validate.
    literal_type : LiteralTypeVar
        The Literal type against which to validate the input_value.

    Raises
    ------
    TypeError
        If input_value is not a string.
    ValueError
        If input_value is not among the valid types in literal_type.
    """
    valid_types = get_args(literal_type)
    if not isinstance(input_value, str):
        raise TypeError(
            f"input_value must be a string. Got {type(input_value).__name__} instead."
        )
    if input_value.lower() not in valid_types:
        raise ValueError(
            f"Invalid input_value '{input_value}'. Expected one of {', '.join(valid_types)}."
        )


def validate_rng(rng: RngTypes, allow_seed: bool = True) -> Generator:
    """Validate the input random number generator.

    This function validates if the input random number generator is an instance of
    the numpy.random.Generator class or an integer. If allow_seed is True, the input
    can also be an integer, which will be used to seed the default random number
    generator.

    Parameters
    ----------
    rng : RngTypes
        The input random number generator.
    allow_seed : bool, optional
        Whether to allow the input to be an integer. Default is True.

    Returns
    -------
    Generator
        The validated random number generator.

    Raises
    ------
    TypeError
        If rng is not an instance of the numpy.random.Generator class or an integer.
    ValueError
        If rng is an integer and it is negative or greater than or equal to 2**32.
    """
    if rng is not None:
        if allow_seed:
            if not isinstance(rng, (Generator, Integral)):
                raise TypeError(
                    "The random number generator must be an instance of the numpy.random.Generator class, or an integer."
                )
            if isinstance(rng, Integral) and (rng < 0 or rng >= 2**32):
                raise ValueError(
                    "The random seed must be a non-negative integer less than 2**32."
                )
        else:
            if not isinstance(rng, Generator):
                raise TypeError(
                    "The random number generator must be an instance of the numpy.random.Generator class."
                )
    rng = check_generator(rng)
    return rng