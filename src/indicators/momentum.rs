use pyo3::prelude::*;

#[path = "momentum_oscillators.rs"]
mod momentum_oscillators;
#[path = "momentum_rates.rs"]
mod momentum_rates;

pub use momentum_oscillators::{CMO, RSI, WILLR};
pub use momentum_rates::{MOM, ROC, ROCP, ROCR, ROCR100};

pub fn register_classes(m: &Bound<'_, PyModule>) -> PyResult<()> {
    momentum_rates::register_classes(m)?;
    momentum_oscillators::register_classes(m)?;
    Ok(())
}
