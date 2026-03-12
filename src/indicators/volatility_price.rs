use pyo3::prelude::*;
use pyo3_stub_gen::derive::*;
use std::collections::VecDeque;

#[gen_stub_pyclass]
#[pyclass(from_py_object)]
#[derive(Debug, Clone)]
pub struct MEDPRICE {
    current_value: Option<f64>,
}

#[gen_stub_pymethods]
#[pymethods]
impl MEDPRICE {
    #[new]
    pub fn new() -> Self {
        MEDPRICE {
            current_value: None,
        }
    }

    pub fn update(&mut self, high: f64, low: f64) -> Option<f64> {
        self.current_value = Some((high + low) / 2.0);
        self.current_value
    }

    #[getter]
    pub fn value(&self) -> Option<f64> {
        self.current_value
    }
}

#[gen_stub_pyclass]
#[pyclass(from_py_object)]
#[derive(Debug, Clone)]
pub struct TYPPRICE {
    current_value: Option<f64>,
}

#[gen_stub_pymethods]
#[pymethods]
impl TYPPRICE {
    #[new]
    pub fn new() -> Self {
        TYPPRICE {
            current_value: None,
        }
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) -> Option<f64> {
        self.current_value = Some((high + low + close) / 3.0);
        self.current_value
    }

    #[getter]
    pub fn value(&self) -> Option<f64> {
        self.current_value
    }
}

#[gen_stub_pyclass]
#[pyclass(from_py_object)]
#[derive(Debug, Clone)]
pub struct WCLPRICE {
    current_value: Option<f64>,
}

#[gen_stub_pymethods]
#[pymethods]
impl WCLPRICE {
    #[new]
    pub fn new() -> Self {
        WCLPRICE {
            current_value: None,
        }
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) -> Option<f64> {
        self.current_value = Some((high + low + 2.0 * close) / 4.0);
        self.current_value
    }

    #[getter]
    pub fn value(&self) -> Option<f64> {
        self.current_value
    }
}

#[gen_stub_pyclass]
#[pyclass(from_py_object)]
#[derive(Debug, Clone)]
pub struct AVGPRICE {
    current_value: Option<f64>,
}

#[gen_stub_pymethods]
#[pymethods]
impl AVGPRICE {
    #[new]
    pub fn new() -> Self {
        AVGPRICE {
            current_value: None,
        }
    }

    pub fn update(&mut self, open: f64, high: f64, low: f64, close: f64) -> Option<f64> {
        self.current_value = Some((open + high + low + close) / 4.0);
        self.current_value
    }

    #[getter]
    pub fn value(&self) -> Option<f64> {
        self.current_value
    }
}

#[gen_stub_pyclass]
#[pyclass(from_py_object)]
#[derive(Debug, Clone)]
pub struct MIDPRICE {
    period: usize,
    highs: VecDeque<f64>,
    lows: VecDeque<f64>,
    current_value: Option<f64>,
}

#[gen_stub_pymethods]
#[pymethods]
impl MIDPRICE {
    #[new]
    pub fn new(period: usize) -> Self {
        MIDPRICE {
            period,
            highs: VecDeque::with_capacity(period),
            lows: VecDeque::with_capacity(period),
            current_value: None,
        }
    }

    pub fn update(&mut self, high: f64, low: f64) -> Option<f64> {
        self.highs.push_back(high);
        self.lows.push_back(low);
        if self.highs.len() > self.period {
            self.highs.pop_front();
            self.lows.pop_front();
        }
        if self.highs.len() < self.period {
            self.current_value = None;
            return None;
        }
        let max_h = self.highs.iter().fold(f64::NEG_INFINITY, |a, b| a.max(*b));
        let min_l = self.lows.iter().fold(f64::INFINITY, |a, b| a.min(*b));
        self.current_value = Some((max_h + min_l) / 2.0);
        self.current_value
    }

    #[getter]
    pub fn value(&self) -> Option<f64> {
        self.current_value
    }
}

pub fn register_classes(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<MEDPRICE>()?;
    m.add_class::<TYPPRICE>()?;
    m.add_class::<WCLPRICE>()?;
    m.add_class::<AVGPRICE>()?;
    m.add_class::<MIDPRICE>()?;
    Ok(())
}
