import numpy as np
import pytest
from arch import arch_model
from hypothesis import given
from hypothesis import strategies as st
from numpy.random import Generator, default_rng
from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.vector_ar.var_model import VAR
from ts_bs.time_series_simulator import TimeSeriesSimulator
from ts_bs.utils.odds_and_ends import assert_arrays_compare

# TODO: test for generate_samples_sieve
# TODO: test samples are same/different with same/different random seeds

MIN_INT = 0
MAX_INT = 2**32 - 1


# Define some common strategies for generating test data
integer_array = st.lists(
    st.integers(min_value=1, max_value=10), min_size=10, max_size=10
).map(np.array)
float_array = st.lists(
    st.floats(
        allow_nan=False, allow_infinity=False, min_value=-1e10, max_value=1e10
    ),
    min_size=10,
    max_size=10,
).map(lambda x: np.array(x).reshape(-1, 1))
float_array_unique = st.just(np.random.rand(10, 1))


def ar_model_strategy():
    return st.builds(
        lambda data: AutoReg(data, lags=1).fit(), float_array_unique
    )


def arima_model_strategy():
    return st.builds(
        lambda data: ARIMA(data, order=(1, 0, 0)).fit(), float_array_unique
    )


def sarima_model_strategy():
    return st.builds(
        lambda data: SARIMAX(
            data, order=(1, 0, 0), seasonal_order=(0, 0, 0, 0)
        ).fit(),
        float_array_unique,
    )


def var_model_strategy():
    return st.builds(
        lambda data: VAR(data).fit(maxlags=1),
        float_array_unique.map(lambda x: np.column_stack([x, x])),
    )


def arch_model_strategy():
    return st.builds(lambda data: arch_model(data).fit(), float_array_unique)


class TestARModel:
    class TestPassingCases:
        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_valid(self, fitted_model, X_fitted, rng):
            """Test that AR model initialization works with valid inputs."""
            TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_fitted_model_valid(self, fitted_model, X_fitted, rng):
            """Test that AR model fitted_model property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert simulator.fitted_model == fitted_model

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_X_fitted_valid(self, fitted_model, X_fitted, rng):
            """Test that AR model X_fitted property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert np.allclose(simulator.X_fitted, X_fitted)

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_rng_valid(self, fitted_model, X_fitted, rng):
            """Test that AR model rng property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert isinstance(simulator.rng, Generator)

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
            resids_lags=integer_array,
            resids_coefs=float_array,
            resids=float_array,
        )
        def test_simulate_ar_process_valid(
            self,
            fitted_model,
            X_fitted,
            rng,
            resids_lags,
            resids_coefs,
            resids,
        ):
            """Test that AR model simulation works with valid inputs."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulator.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
            resids_lags=integer_array,
            resids_coefs=float_array,
            resids=float_array,
        )
        def test_simulate_ar_process_valid_large_input(
            self,
            fitted_model,
            X_fitted,
            rng,
            resids_lags,
            resids_coefs,
            resids,
        ):
            """Test that AR model simulation works with larger input arrays."""
            large_X_fitted = np.repeat(X_fitted, 10, axis=0)
            large_resids_lags = np.repeat(resids_lags, 10)
            large_resids_coefs = np.repeat(resids_coefs, 10).reshape(1, -1)
            large_resids = np.repeat(resids, 10)
            simulator = TimeSeriesSimulator(fitted_model, large_X_fitted, rng)
            simulator.simulate_ar_process(
                large_resids_lags, large_resids_coefs, large_resids
            )

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            resids_lags=integer_array,
            resids_coefs=float_array,
            resids=float_array,
        )
        def test_simulate_ar_same_rng(
            self, fitted_model, X_fitted, resids_lags, resids_coefs, resids
        ):
            """Test that AR model simulation gives same results with same rng."""
            rng_seed = 12345

            rng1 = np.random.default_rng(rng_seed)
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng1)
            simulated_series1 = simulator1.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )

            rng2 = np.random.default_rng(rng_seed)
            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng2)
            simulated_series2 = simulator2.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )
            assert_arrays_compare(simulated_series1, simulated_series2)

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            resids_lags=integer_array,
            resids_coefs=float_array,
            resids=float_array,
        )
        def test_simulate_ar_different_rng(
            self, fitted_model, X_fitted, resids_lags, resids_coefs, resids
        ):
            """Test that AR model simulation gives different results with different rng."""
            rng = np.random.default_rng()
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulated_series1 = simulator1.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )

            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulated_series2 = simulator2.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )

            assert_arrays_compare(
                simulated_series1, simulated_series2, check_same=False
            )

            simulated_series3 = simulator2.simulate_ar_process(
                resids_lags, resids_coefs.reshape(1, -1), resids
            )

            assert_arrays_compare(
                simulated_series2, simulated_series3, check_same=False
            )

    class TestFailingCases:
        @given(
            fitted_model=st.none() | st.integers() | st.floats() | st.text(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_fitted_model(self, fitted_model, X_fitted, rng):
            """Test that AR model initialization fails with invalid fitted_model."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
            resids_lags=st.none() | float_array | st.text(),
            resids_coefs=float_array,
            resids=float_array,
        )
        def test_simulate_ar_process_invalid_resids_lags(
            self,
            fitted_model,
            X_fitted,
            rng,
            resids_lags,
            resids_coefs,
            resids,
        ):
            """Test that AR model simulation fails with invalid resids_lags."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            with pytest.raises((ValueError, TypeError)):
                simulator.simulate_ar_process(
                    resids_lags, resids_coefs.reshape(1, -1), resids
                )

        @given(
            fitted_model=ar_model_strategy(),
            X_fitted=st.none() | integer_array | st.text(),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_X_fitted(self, fitted_model, X_fitted, rng):
            """Test that AR model initialization fails with invalid X_fitted."""
            if not isinstance(X_fitted, np.ndarray):
                with pytest.raises(TypeError):
                    TimeSeriesSimulator(fitted_model, X_fitted, rng)


class TestARIMAModel:
    class TestPassingCases:
        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_valid(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model initialization works with valid inputs."""
            TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_fitted_model_valid(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model fitted_model property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert simulator.fitted_model == fitted_model

        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_X_fitted_valid(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model X_fitted property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert np.allclose(simulator.X_fitted, X_fitted)

        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_rng_valid(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model rng property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert isinstance(simulator.rng, Generator)

        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_simulate_non_ar_process_valid(
            self, fitted_model, X_fitted, rng
        ):
            """Test that ARIMA model simulation works with valid inputs."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulator.simulate_non_ar_process()

        # TODO: even with the same rng object, simulation results are different. Investigate why.
        '''
        @given(fitted_model=arima_model_strategy(), X_fitted=float_array)
        def test_simulate_non_ar_same_rng(self, fitted_model, X_fitted):
            """Test that ARIMA model simulation gives same results with same rng"""
            rng_seed = 12345

            rng1 = np.random.default_rng(rng_seed)
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng1)
            simulated_series1 = simulator1.simulate_non_ar_process()

            rng2 = np.random.default_rng(rng_seed)
            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng2)
            simulated_series2 = simulator2.simulate_non_ar_process()

            print(f"simulated_series1 = {simulated_series1}")
            print(f"simulated_series2 = {simulated_series2}")
            print("\n")
            assert_arrays_compare(
                simulated_series1, simulated_series2)
        '''

    class TestFailingCases:
        @given(
            fitted_model=st.none() | st.integers() | st.floats() | st.text(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_fitted_model(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model initialization fails with invalid fitted_model."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=arima_model_strategy(),
            X_fitted=st.none() | integer_array | st.text(),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_X_fitted(self, fitted_model, X_fitted, rng):
            """Test that ARIMA model initialization fails with invalid X_fitted."""
            if not isinstance(X_fitted, np.ndarray):
                with pytest.raises(TypeError):
                    TimeSeriesSimulator(fitted_model, X_fitted, rng)


class TestSARIMAModel:
    class TestPassingCases:
        @given(
            fitted_model=sarima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_valid(self, fitted_model, X_fitted, rng):
            """Test that SARIMA model initialization works with valid inputs."""
            TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=sarima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_fitted_model_valid(self, fitted_model, X_fitted, rng):
            """Test that SARIMA model fitted_model property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert simulator.fitted_model == fitted_model

        @given(
            fitted_model=sarima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_X_fitted_valid(self, fitted_model, X_fitted, rng):
            """Test that SARIMA model X_fitted property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert np.allclose(simulator.X_fitted, X_fitted)

        @given(
            fitted_model=sarima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_rng_valid(self, fitted_model, X_fitted, rng):
            """Test that SARIMA model rng property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert isinstance(simulator.rng, Generator)

        @given(
            fitted_model=sarima_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_simulate_non_ar_process_valid(
            self, fitted_model, X_fitted, rng
        ):
            """Test that SARIMA model simulation works with valid inputs."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulator.simulate_non_ar_process()

        # TODO: even with the same rng object, simulation results are different. Investigate why.
        '''
        @given(fitted_model=sarima_model_strategy(), X_fitted=float_array)
        def test_simulate_non_ar_same_rng(self, fitted_model, X_fitted):
            """Test that SARIMA model simulation gives same results with same rng."""
            rng_seed = 12345

            rng1 = np.random.default_rng(rng_seed)
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng1)
            simulated_series1 = simulator1.simulate_non_ar_process()

            rng2 = np.random.default_rng(rng_seed)
            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng2)
            simulated_series2 = simulator2.simulate_non_ar_process()

            print(f"simulated_series1 = {simulated_series1}")
            print(f"simulated_series2 = {simulated_series2}")
            print("\n")
            assert_arrays_compare(
                simulated_series1, simulated_series2)
        '''

    class TestFailingCases:
        @given(
            fitted_model=st.none() | st.integers() | st.floats() | st.text(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_fitted_model(self, fitted_model, X_fitted, rng):
            """Test that SARIMA model initialization fails with invalid fitted_model."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)


class TestVARModel:
    class TestPassingCases:
        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_valid(self, fitted_model, X_fitted, rng):
            """Test that VAR model initialization works with valid inputs."""
            TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_fitted_model_valid(self, fitted_model, X_fitted, rng):
            """Test that VAR model fitted_model property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert simulator.fitted_model == fitted_model

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_X_fitted_valid(self, fitted_model, X_fitted, rng):
            """Test that VAR model X_fitted property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert np.allclose(simulator.X_fitted, X_fitted)

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_rng_valid(self, fitted_model, X_fitted, rng):
            """Test that VAR model rng property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert isinstance(simulator.rng, Generator)

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_simulate_non_ar_process_valid(
            self, fitted_model, X_fitted, rng
        ):
            """Test that VAR model simulation works with valid inputs."""
            print(f"X_fitted.shape = {X_fitted.shape}")
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            print(f"simulator.X_fitted.shape = {simulator.X_fitted.shape}")
            print(f"simulator.burnin = {simulator.burnin}")
            simulator.simulate_non_ar_process()

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
        )
        def test_simulate_non_ar_same_rng(self, fitted_model, X_fitted):
            """Test that SARIMA model simulation gives same results with same rng."""
            rng_seed = 12345

            rng1 = np.random.default_rng(rng_seed)
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng1)
            simulated_series1 = simulator1.simulate_non_ar_process()

            rng2 = np.random.default_rng(rng_seed)
            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng2)
            simulated_series2 = simulator2.simulate_non_ar_process()

            print(f"simulated_series1 = {simulated_series1}")
            print(f"simulated_series2 = {simulated_series2}")
            print("\n")
            assert_arrays_compare(simulated_series1, simulated_series2)

        @given(
            fitted_model=var_model_strategy(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
        )
        def test_simulate_non_ar_different_rng(self, fitted_model, X_fitted):
            """Test that SARIMA model simulation gives same results with same rng."""
            rng = np.random.default_rng()
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulated_series1 = simulator1.simulate_non_ar_process()

            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulated_series2 = simulator2.simulate_non_ar_process()

            assert_arrays_compare(
                simulated_series1, simulated_series2, check_same=False
            )

            simulated_series3 = simulator2.simulate_non_ar_process()

            assert_arrays_compare(
                simulated_series2, simulated_series3, check_same=False
            )

    class TestFailingCases:
        @given(
            fitted_model=st.none() | st.integers() | st.floats() | st.text(),
            X_fitted=float_array.map(lambda x: np.column_stack([x, x])),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_fitted_model(self, fitted_model, X_fitted, rng):
            """Test that VAR model initialization fails with invalid fitted_model."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)


class TestARCHModel:
    class TestPassingCases:
        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_valid(self, fitted_model, X_fitted, rng):
            """Test that ARCH model initialization works with valid inputs."""
            TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_fitted_model_valid(self, fitted_model, X_fitted, rng):
            """Test that ARCH model fitted_model property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert simulator.fitted_model == fitted_model

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_X_fitted_valid(self, fitted_model, X_fitted, rng):
            """Test that ARCH model X_fitted property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert np.allclose(simulator.X_fitted, X_fitted)

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_rng_valid(self, fitted_model, X_fitted, rng):
            """Test that ARCH model rng property getter and setter work correctly."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            assert isinstance(simulator.rng, Generator)

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_simulate_non_ar_process_valid(
            self, fitted_model, X_fitted, rng
        ):
            """Test that ARCH model simulation works with valid inputs."""
            simulator = TimeSeriesSimulator(fitted_model, X_fitted, rng)
            simulator.simulate_non_ar_process()

        # TODO: even with the same rng object, simulation results are different. Investigate why.
        '''
        @given(fitted_model=arch_model_strategy(), X_fitted=float_array)
        def test_simulate_non_ar_same_rng(self, fitted_model, X_fitted):
            """Test that SARIMA model simulation gives same results with same rng."""
            rng_seed = 12345

            rng1 = np.random.default_rng(rng_seed)
            simulator1 = TimeSeriesSimulator(fitted_model, X_fitted, rng1)
            simulated_series1 = simulator1.simulate_non_ar_process()

            rng2 = np.random.default_rng(rng_seed)
            simulator2 = TimeSeriesSimulator(fitted_model, X_fitted, rng2)
            simulated_series2 = simulator2.simulate_non_ar_process()

            print(f"simulated_series1 = {simulated_series1}")
            print(f"simulated_series2 = {simulated_series2}")
            print("\n")
            assert_arrays_compare(
                simulated_series1, simulated_series2)
        '''

    class TestFailingCases:
        @given(
            fitted_model=st.none() | st.integers() | st.floats() | st.text(),
            X_fitted=float_array,
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_fitted_model(self, fitted_model, X_fitted, rng):
            """Test that ARCH model initialization fails with invalid fitted_model."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=st.none() | st.integers() | st.text(),
            rng=st.none()
            | st.integers(min_value=MIN_INT, max_value=MAX_INT)
            | st.just(default_rng()),
        )
        def test_init_invalid_X_fitted(self, fitted_model, X_fitted, rng):
            """Test that ARCH model initialization fails with invalid X_fitted."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)

        @given(
            fitted_model=arch_model_strategy(),
            X_fitted=float_array,
            rng=st.floats() | st.text(),
        )
        def test_init_invalid_rng(self, fitted_model, X_fitted, rng):
            """Test that ARCH model initialization fails with invalid rng."""
            with pytest.raises(TypeError):
                TimeSeriesSimulator(fitted_model, X_fitted, rng)