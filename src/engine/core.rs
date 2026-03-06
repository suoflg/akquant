use chrono::{DateTime, NaiveDate, NaiveTime, TimeZone, Utc};
use indicatif::ProgressBar;
use pyo3::exceptions::PyRuntimeError;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3_stub_gen::derive::*;
use rust_decimal::prelude::*;
use std::collections::{BinaryHeap, HashMap};
use std::sync::{Arc, RwLock};
use uuid::Uuid;

// use crate::analysis::{BacktestResult, PositionSnapshot};
use crate::clock::Clock;
use crate::context::StrategyContext;
use crate::event::Event;
use crate::event_manager::EventManager;
use crate::execution::ExecutionClient;
use crate::history::HistoryBuffer;
use crate::market::corporate_action::CorporateActionManager;
use crate::market::manager::MarketManager;
use crate::model::{
    ExecutionMode, Instrument, Order, Timer, Trade,
};
use crate::pipeline::stages::{
    ChannelProcessor, CleanupProcessor, DataProcessor, ExecutionPhase, ExecutionProcessor,
    StatisticsProcessor, StrategyProcessor,
};
use crate::pipeline::PipelineRunner;
use crate::risk::RiskManager;
use crate::settlement::SettlementManager;
use crate::statistics::StatisticsManager;

use super::state::SharedState;

/// 主回测引擎.
///
/// :ivar feed: 数据源
/// :ivar portfolio: 投资组合
/// :ivar orders: 订单列表
/// :ivar trades: 成交列表
#[gen_stub_pyclass]
#[pyclass]
pub struct Engine {
    pub(crate) state: SharedState,
    pub(crate) last_prices: HashMap<String, Decimal>,
    pub(crate) instruments: HashMap<String, Instrument>,
    pub(crate) current_date: Option<NaiveDate>,
    pub(crate) market_manager: MarketManager,
    pub(crate) corporate_action_manager: CorporateActionManager,
    pub(crate) execution_model: Box<dyn ExecutionClient>,
    pub(crate) execution_mode: ExecutionMode,
    pub(crate) clock: Clock,
    pub(crate) timers: BinaryHeap<Timer>, // Min-Heap via Timer's Ord implementation
    pub(crate) force_session_continuous: bool,
    #[pyo3(get, set)]
    pub risk_manager: RiskManager,
    pub(crate) timezone_offset: i32,
    pub(crate) history_buffer: Arc<RwLock<HistoryBuffer>>,
    pub(crate) initial_cash: Decimal,
    // Components
    pub(crate) event_manager: EventManager,
    pub(crate) statistics_manager: StatisticsManager,
    pub(crate) settlement_manager: SettlementManager,
    // Pipeline state
    pub(crate) current_event: Option<Event>,
    pub(crate) bar_count: usize,
    pub(crate) progress_bar: Option<ProgressBar>,
    pub(crate) strategy_context: Option<Py<StrategyContext>>,
    pub(crate) snapshot_time: i64,
    pub(crate) stream_callback: Option<Py<PyAny>>,
    pub(crate) stream_run_id: Option<String>,
    pub(crate) stream_seq: u64,
    pub(crate) stream_progress_interval: usize,
    pub(crate) stream_equity_interval: usize,
    pub(crate) stream_batch_size: usize,
    pub(crate) stream_max_buffer: usize,
    pub(crate) stream_buffer: Vec<PendingStreamEvent>,
    pub(crate) stream_fail_fast_on_callback_error: bool,
    pub(crate) stream_callback_error_count: u64,
    pub(crate) stream_callback_last_error: Option<String>,
    pub(crate) stream_fatal_error: Option<String>,
    pub(crate) stream_dropped_event_count: u64,
    pub(crate) stream_dropped_event_count_by_type: HashMap<String, u64>,
    pub(crate) stream_mode: String,
    pub(crate) stream_sampling_enabled: bool,
    pub(crate) stream_drop_non_critical: bool,
}

pub(crate) struct PendingStreamEvent {
    pub(crate) event_type: String,
    pub(crate) symbol: Option<String>,
    pub(crate) level: String,
    pub(crate) payload: Vec<(String, String)>,
}

// Internal implementation of Engine (not exposed to Python)
impl Engine {
    pub(crate) fn set_stream_callback_internal(&mut self, callback: Option<Py<PyAny>>) {
        self.stream_callback = callback;
        self.stream_run_id = None;
        self.stream_seq = 0;
        self.stream_buffer.clear();
        self.stream_callback_error_count = 0;
        self.stream_callback_last_error = None;
        self.stream_fatal_error = None;
        self.stream_dropped_event_count = 0;
        self.stream_dropped_event_count_by_type.clear();
    }

    pub(crate) fn set_stream_options_internal(
        &mut self,
        progress_interval: usize,
        equity_interval: usize,
        batch_size: usize,
        max_buffer: usize,
        error_mode: &str,
        stream_mode: &str,
    ) {
        self.stream_progress_interval = progress_interval.max(1);
        self.stream_equity_interval = equity_interval.max(1);
        self.stream_batch_size = batch_size.max(1);
        self.stream_max_buffer = max_buffer.max(1);
        self.stream_fail_fast_on_callback_error = error_mode == "fail_fast";
        if stream_mode == "audit" {
            self.stream_mode = "audit".to_string();
            self.stream_sampling_enabled = false;
            self.stream_drop_non_critical = false;
        } else {
            self.stream_mode = "observability".to_string();
            self.stream_sampling_enabled = true;
            self.stream_drop_non_critical = true;
        }
    }

    pub(crate) fn start_stream_run(
        &mut self,
        py: Python<'_>,
        total_events: Option<usize>,
    ) {
        if self.stream_callback.is_none() {
            self.stream_run_id = None;
            self.stream_seq = 0;
            self.stream_buffer.clear();
            self.stream_callback_error_count = 0;
            self.stream_callback_last_error = None;
            self.stream_fatal_error = None;
            self.stream_dropped_event_count = 0;
            self.stream_dropped_event_count_by_type.clear();
            return;
        }
        self.stream_seq = 0;
        self.stream_run_id = Some(Uuid::new_v4().to_string());
        self.stream_callback_error_count = 0;
        self.stream_callback_last_error = None;
        self.stream_fatal_error = None;
        self.stream_dropped_event_count = 0;
        self.stream_dropped_event_count_by_type.clear();

        let mut payload = HashMap::new();
        payload.insert("total_events", total_events.unwrap_or(0).to_string());
        payload.insert("execution_mode", format!("{:?}", self.execution_mode));
        self.emit_stream_event(py, "started", None, "info", payload);
    }

    pub(crate) fn emit_stream_event(
        &mut self,
        py: Python<'_>,
        event_type: &str,
        symbol: Option<&str>,
        level: &str,
        payload: HashMap<&str, String>,
    ) {
        let (Some(_), Some(_)) = (&self.stream_callback, &self.stream_run_id) else {
            return;
        };

        if self.stream_sampling_enabled
            && event_type == "progress"
            && self.bar_count % self.stream_progress_interval != 0
        {
            return;
        }
        if self.stream_sampling_enabled
            && event_type == "equity"
            && self.bar_count % self.stream_equity_interval != 0
        {
            return;
        }

        let is_critical = matches!(
            event_type,
            "started" | "order" | "trade" | "risk" | "error" | "finished"
        );
        if self.stream_buffer.len() >= self.stream_max_buffer {
            if is_critical || !self.stream_drop_non_critical {
                self.flush_stream_events(py);
            } else {
                self.record_dropped_stream_event(event_type);
                return;
            }
        }

        let mut payload_vec = Vec::new();
        for (k, v) in payload {
            payload_vec.push((k.to_string(), v));
        }
        self.stream_buffer.push(PendingStreamEvent {
            event_type: event_type.to_string(),
            symbol: symbol.map(str::to_string),
            level: level.to_string(),
            payload: payload_vec,
        });

        if is_critical || self.stream_buffer.len() >= self.stream_batch_size {
            self.flush_stream_events(py);
        }
    }

    pub(crate) fn flush_stream_events(&mut self, py: Python<'_>) {
        let (Some(callback_ref), Some(run_id_ref)) = (&self.stream_callback, &self.stream_run_id) else {
            self.stream_buffer.clear();
            return;
        };
        let callback = callback_ref.clone_ref(py);
        let run_id = run_id_ref.clone();
        if self.stream_buffer.is_empty() {
            return;
        }

        for pending in self.stream_buffer.drain(..) {
            self.stream_seq = self.stream_seq.saturating_add(1);
            let event_dict = PyDict::new(py);
            if event_dict.set_item("run_id", run_id.as_str()).is_err()
                || event_dict.set_item("seq", self.stream_seq).is_err()
                || event_dict
                    .set_item("ts", self.clock.timestamp().unwrap_or(0))
                    .is_err()
                || event_dict
                    .set_item("event_type", pending.event_type.as_str())
                    .is_err()
                || event_dict.set_item("symbol", pending.symbol).is_err()
                || event_dict.set_item("level", pending.level.as_str()).is_err()
            {
                continue;
            }

            let payload_dict = PyDict::new(py);
            for (k, v) in pending.payload {
                if payload_dict.set_item(k, v).is_err() {
                    continue;
                }
            }
            if event_dict.set_item("payload", payload_dict).is_err() {
                continue;
            }
            if let Err(err) = callback.bind(py).call1((event_dict,)) {
                self.stream_callback_error_count =
                    self.stream_callback_error_count.saturating_add(1);
                let message = err.to_string();
                self.stream_callback_last_error = Some(message.clone());
                if self.stream_fail_fast_on_callback_error {
                    self.stream_fatal_error = Some(format!(
                        "stream callback failed in fail_fast mode: {}",
                        message
                    ));
                    break;
                }
            }
        }
    }

    pub(crate) fn finish_stream_run(
        &mut self,
        py: Python<'_>,
        status: &str,
        reason: Option<&str>,
    ) {
        if self.stream_callback.is_none() {
            self.stream_run_id = None;
            self.stream_seq = 0;
            self.stream_buffer.clear();
            self.stream_callback_error_count = 0;
            self.stream_callback_last_error = None;
            self.stream_fatal_error = None;
            self.stream_dropped_event_count = 0;
            self.stream_dropped_event_count_by_type.clear();
            return;
        }

        let mut payload = HashMap::new();
        payload.insert("status", status.to_string());
        payload.insert(
            "processed_events",
            self.bar_count.to_string(),
        );
        payload.insert(
            "total_trades",
            self.state.order_manager.trades.len().to_string(),
        );
        payload.insert(
            "callback_error_count",
            self.stream_callback_error_count.to_string(),
        );
        payload.insert(
            "dropped_event_count",
            self.stream_dropped_event_count.to_string(),
        );
        payload.insert(
            "dropped_event_count_by_type",
            self.format_stream_dropped_event_counts(),
        );
        payload.insert("stream_mode", self.stream_mode.clone());
        payload.insert(
            "sampling_enabled",
            self.stream_sampling_enabled.to_string(),
        );
        payload.insert(
            "backpressure_policy",
            if self.stream_drop_non_critical {
                "drop_non_critical".to_string()
            } else {
                "block".to_string()
            },
        );
        if let Some(message) = reason {
            payload.insert("reason", message.to_string());
        }
        if let Some(message) = &self.stream_callback_last_error {
            payload.insert("last_callback_error", message.clone());
        }
        self.emit_stream_event(py, "finished", None, "info", payload);
        self.flush_stream_events(py);
        self.stream_run_id = None;
        self.stream_buffer.clear();
    }

    pub(crate) fn record_dropped_stream_event(&mut self, event_type: &str) {
        self.stream_dropped_event_count =
            self.stream_dropped_event_count.saturating_add(1);
        let counter = self
            .stream_dropped_event_count_by_type
            .entry(event_type.to_string())
            .or_insert(0);
        *counter = counter.saturating_add(1);
    }

    pub(crate) fn format_stream_dropped_event_counts(&self) -> String {
        if self.stream_dropped_event_count_by_type.is_empty() {
            return String::new();
        }
        let mut entries: Vec<(&String, &u64)> =
            self.stream_dropped_event_count_by_type.iter().collect();
        entries.sort_by(|(left, _), (right, _)| left.cmp(right));
        entries
            .into_iter()
            .map(|(event_type, count)| format!("{}={}", event_type, count))
            .collect::<Vec<String>>()
            .join(",")
    }

    pub(crate) fn raise_stream_fatal_error_if_any(&mut self) -> PyResult<()> {
        if let Some(message) = self.stream_fatal_error.take() {
            return Err(PyRuntimeError::new_err(message));
        }
        Ok(())
    }

    pub(crate) fn create_context(
        &self,
        active_orders: Arc<Vec<Order>>,
        step_trades: Vec<Trade>,
    ) -> StrategyContext {
        // Create a temporary context for the strategy to use
        StrategyContext::new(crate::context::ContextInit {
            cash: self.state.portfolio.cash,
            positions: self.state.portfolio.positions.clone(),
            available_positions: self.state.portfolio.available_positions.clone(),
            session: self.clock.session,
            current_time: self.clock.timestamp().unwrap_or(0),
            active_orders,
            closed_trades: self.state.order_manager.trade_tracker.closed_trades.clone(),
            recent_trades: step_trades,
            history_buffer: Some(self.history_buffer.clone()),
            event_tx: Some(self.event_manager.sender()),
            risk_config: self.risk_manager.config.clone(),
        })
    }

    pub(crate) fn datetime_from_ns(timestamp: i64) -> DateTime<Utc> {
        let secs = timestamp.div_euclid(1_000_000_000);
        let nanos = timestamp.rem_euclid(1_000_000_000) as u32;
        Utc.timestamp_opt(secs, nanos)
            .single()
            .expect("Invalid timestamp")
    }

    pub(crate) fn local_datetime_from_ns(timestamp: i64, offset_secs: i32) -> DateTime<Utc> {
        let offset_ns = i64::from(offset_secs) * 1_000_000_000;
        Self::datetime_from_ns(timestamp + offset_ns)
    }

    pub(crate) fn parse_time_string(value: &str) -> PyResult<NaiveTime> {
        if let Ok(t) = NaiveTime::parse_from_str(value, "%H:%M:%S") {
            return Ok(t);
        }
        if let Ok(t) = NaiveTime::parse_from_str(value, "%H:%M") {
            return Ok(t);
        }
        Err(PyValueError::new_err(format!(
            "Invalid time format: {}",
            value
        )))
    }

    pub(crate) fn call_strategy(
        &mut self,
        strategy: &Bound<'_, PyAny>,
        event: &Event,
    ) -> PyResult<(Vec<Order>, Vec<Timer>, Vec<String>)> {
        // Update Last Price and Trigger Strategy
        match event {
            Event::Bar(b) => {
                self.last_prices.insert(b.symbol.clone(), b.close);
                let step_trades = std::mem::take(&mut self.state.order_manager.current_step_trades);
                // Share active orders via Arc
                let active_orders = Arc::new(self.state.order_manager.active_orders.clone());

                // Reuse or create StrategyContext
                let py_ctx = if let Some(ref ctx) = self.strategy_context {
                    // Reuse existing context
                    Python::attach(|py| {
                        let py_ctx = ctx.clone_ref(py);
                        {
                            let mut ctx_mut = py_ctx.borrow_mut(py);
                            ctx_mut.update_state(crate::context::ContextUpdate {
                                cash: self.state.portfolio.cash,
                                positions: self.state.portfolio.positions.clone(),
                                available_positions: self.state.portfolio.available_positions.clone(),
                                session: self.clock.session,
                                current_time: self.clock.timestamp().unwrap_or(0),
                                active_orders,
                                recent_trades: step_trades,
                            });
                        }
                        Ok::<_, PyErr>(py_ctx)
                    })?
                } else {
                    // Create new context (first time)
                    let ctx = self.create_context(active_orders, step_trades);
                    let (py_ctx, persistent_ref) = Python::attach(|py| {
                        let py_ctx = Py::new(py, ctx).unwrap();
                        Ok::<_, PyErr>((py_ctx.clone_ref(py), py_ctx.clone_ref(py)))
                    })?;
                    self.strategy_context = Some(persistent_ref);
                    py_ctx
                };

                let args = Python::attach(|py| {
                     let bar = b.clone();
                     (bar, py_ctx.clone_ref(py))
                });

                strategy.call_method1("_on_bar_event", args)?;

                // Extract orders and timers
                let mut new_orders = Vec::new();
                let mut new_timers = Vec::new();
                let mut canceled_ids = Vec::new();
                Python::attach(|py| {
                    let ctx_ref = py_ctx.borrow(py);
                    // Read from RwLock
                    if let Ok(orders) = ctx_ref.orders_arc.read() {
                        new_orders.extend(orders.clone());
                    }
                    if let Ok(timers) = ctx_ref.timers_arc.read() {
                        new_timers.extend(timers.clone());
                    }
                    if let Ok(canceled) = ctx_ref.canceled_order_ids_arc.read() {
                        canceled_ids.extend(canceled.clone());
                    }
                });
                Ok((new_orders, new_timers, canceled_ids))
            }
            Event::Tick(t) => {
                self.last_prices.insert(t.symbol.clone(), t.price);
                let step_trades = std::mem::take(&mut self.state.order_manager.current_step_trades);
                let active_orders = Arc::new(self.state.order_manager.active_orders.clone());

                 // Reuse or create StrategyContext
                let py_ctx = if let Some(ref ctx) = self.strategy_context {
                    // Reuse existing context
                    Python::attach(|py| {
                        let py_ctx = ctx.clone_ref(py);
                        {
                            let mut ctx_mut = py_ctx.borrow_mut(py);
                            ctx_mut.update_state(crate::context::ContextUpdate {
                                cash: self.state.portfolio.cash,
                                positions: self.state.portfolio.positions.clone(),
                                available_positions: self.state.portfolio.available_positions.clone(),
                                session: self.clock.session,
                                current_time: self.clock.timestamp().unwrap_or(0),
                                active_orders,
                                recent_trades: step_trades,
                            });
                        }
                        Ok::<_, PyErr>(py_ctx)
                    })?
                } else {
                    // Create new context (first time)
                    let ctx = self.create_context(active_orders, step_trades);
                    let (py_ctx, persistent_ref) = Python::attach(|py| {
                        let py_ctx = Py::new(py, ctx).unwrap();
                        Ok::<_, PyErr>((py_ctx.clone_ref(py), py_ctx.clone_ref(py)))
                    })?;
                    self.strategy_context = Some(persistent_ref);
                    py_ctx
                };

                let args = Python::attach(|py| {
                     let tick = t.clone();
                     (tick, py_ctx.clone_ref(py))
                });

                strategy.call_method1("_on_tick_event", args)?;

                // Extract orders and timers
                let mut new_orders = Vec::new();
                let mut new_timers = Vec::new();
                let mut canceled_ids = Vec::new();
                Python::attach(|py| {
                    let ctx_ref = py_ctx.borrow(py);
                    if let Ok(orders) = ctx_ref.orders_arc.read() {
                        new_orders.extend(orders.clone());
                    }
                    if let Ok(timers) = ctx_ref.timers_arc.read() {
                        new_timers.extend(timers.clone());
                    }
                    if let Ok(canceled) = ctx_ref.canceled_order_ids_arc.read() {
                        canceled_ids.extend(canceled.clone());
                    }
                });
                Ok((new_orders, new_timers, canceled_ids))
            }
            Event::Timer(timer) => {
                let step_trades = std::mem::take(&mut self.state.order_manager.current_step_trades);
                let active_orders = Arc::new(self.state.order_manager.active_orders.clone());

                 // Reuse or create StrategyContext
                let py_ctx = if let Some(ref ctx) = self.strategy_context {
                    // Reuse existing context
                    Python::attach(|py| {
                        let py_ctx = ctx.clone_ref(py);
                        {
                            let mut ctx_mut = py_ctx.borrow_mut(py);
                            ctx_mut.update_state(crate::context::ContextUpdate {
                                cash: self.state.portfolio.cash,
                                positions: self.state.portfolio.positions.clone(),
                                available_positions: self.state.portfolio.available_positions.clone(),
                                session: self.clock.session,
                                current_time: self.clock.timestamp().unwrap_or(0),
                                active_orders,
                                recent_trades: step_trades,
                            });
                        }
                        Ok::<_, PyErr>(py_ctx)
                    })?
                } else {
                    // Create new context (first time)
                    let ctx = self.create_context(active_orders, step_trades);
                    let (py_ctx, persistent_ref) = Python::attach(|py| {
                        let py_ctx = Py::new(py, ctx).unwrap();
                        Ok::<_, PyErr>((py_ctx.clone_ref(py), py_ctx.clone_ref(py)))
                    })?;
                    self.strategy_context = Some(persistent_ref);
                    py_ctx
                };

                let args = Python::attach(|py| {
                     let payload = timer.payload.as_str();
                     (payload, py_ctx.clone_ref(py))
                });

                strategy.call_method1("_on_timer_event", args)?;

                // Extract orders and timers
                let mut new_orders = Vec::new();
                let mut new_timers = Vec::new();
                let mut canceled_ids = Vec::new();
                Python::attach(|py| {
                    let ctx_ref = py_ctx.borrow(py);
                    if let Ok(orders) = ctx_ref.orders_arc.read() {
                        new_orders.extend(orders.clone());
                    }
                    if let Ok(timers) = ctx_ref.timers_arc.read() {
                        new_timers.extend(timers.clone());
                    }
                    if let Ok(canceled) = ctx_ref.canceled_order_ids_arc.read() {
                        canceled_ids.extend(canceled.clone());
                    }
                });
                Ok((new_orders, new_timers, canceled_ids))
            }
            Event::OrderRequest(_) | Event::OrderValidated(_) | Event::ExecutionReport(_, _) => {
                Ok((Vec::new(), Vec::new(), Vec::new()))
            }
        }
    }

    pub(crate) fn build_pipeline(&self) -> PipelineRunner {
        let mut pipeline = PipelineRunner::new();
        // 1. Process events from previous iteration (or init)
        pipeline.add_processor(Box::new(ChannelProcessor));

        // 2. Fetch new Data Event
        pipeline.add_processor(Box::new(DataProcessor::new()));

        // 3. Pre-Strategy Execution (Match Pending Orders)
        // For NextOpen/NextAverage: Matches orders generated in previous bar against current bar.
        pipeline.add_processor(Box::new(ExecutionProcessor::new(ExecutionPhase::PreStrategy)));

        // 4. Process Fills from Pre-Execution immediately (Update Portfolio before Strategy)
        pipeline.add_processor(Box::new(ChannelProcessor));

        // 5. Run Strategy
        pipeline.add_processor(Box::new(StrategyProcessor));

        // 6. Process Order Requests from Strategy immediately (Validate -> Pending)
        pipeline.add_processor(Box::new(ChannelProcessor));

        // 7. Post-Strategy Execution
        // For CurrentClose: Matches orders generated in current bar against current bar.
        pipeline.add_processor(Box::new(ExecutionProcessor::new(ExecutionPhase::PostStrategy)));

        // 8. Process Fills from Post-Execution
        pipeline.add_processor(Box::new(ChannelProcessor));

        // 9. Statistics & Cleanup
        pipeline.add_processor(Box::new(StatisticsProcessor));
        pipeline.add_processor(Box::new(CleanupProcessor));

        pipeline
    }
}
