use rust_decimal::Decimal;
use std::collections::HashMap;
use std::sync::Arc;
use serde::{Deserialize, Serialize};

use crate::data::DataFeed;
use crate::order_manager::OrderManager;
use crate::portfolio::Portfolio;

/// Shared state container for Engine
pub struct SharedState {
    pub portfolio: Portfolio,
    pub order_manager: OrderManager,
    pub feed: DataFeed,
}

impl SharedState {
    pub fn new(initial_cash: Decimal) -> Self {
        Self {
            portfolio: Portfolio {
                cash: initial_cash,
                positions: Arc::new(HashMap::new()),
                available_positions: Arc::new(HashMap::new()),
            },
            order_manager: OrderManager::new(),
            feed: DataFeed::new(),
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct EngineSnapshot {
    pub current_time: i64,
    pub portfolio: Portfolio,
    pub order_manager: OrderManager,
}
