use crate::error::AkQuantError;
use crate::model::{Order, OrderSide};
use rust_decimal::Decimal;
use rust_decimal::prelude::*;

use super::rule::{RiskCheckContext, RiskRule};

/// Check restricted list
#[derive(Debug, Clone)]
pub struct RestrictedListRule;

impl RiskRule for RestrictedListRule {
    fn name(&self) -> &'static str {
        "RestrictedListRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if ctx.config.restricted_list.contains(&order.symbol) {
            return Err(AkQuantError::OrderError(format!(
                "Risk: Symbol {} is restricted",
                order.symbol
            )));
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max order size
#[derive(Debug, Clone)]
pub struct MaxOrderSizeRule;

impl RiskRule for MaxOrderSizeRule {
    fn name(&self) -> &'static str {
        "MaxOrderSizeRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_size) = ctx.config.max_order_size
            && order.quantity > max_size
        {
            return Err(AkQuantError::OrderError(format!(
                "Risk: Order quantity {} exceeds limit {}",
                order.quantity, max_size
            )));
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max order value
#[derive(Debug, Clone)]
pub struct MaxOrderValueRule;

impl RiskRule for MaxOrderValueRule {
    fn name(&self) -> &'static str {
        "MaxOrderValueRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_value) = ctx.config.max_order_value {
            let price = if let Some(p) = order.price {
                Some(p)
            } else {
                ctx.current_prices.get(&order.symbol).copied()
            };

            if let Some(p) = price {
                let value = p * order.quantity;
                if value > max_value {
                    return Err(AkQuantError::OrderError(format!(
                        "Risk: Order value {value} exceeds limit {max_value}",
                    )));
                }
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max position size
#[derive(Debug, Clone)]
pub struct MaxPositionSizeRule;

impl RiskRule for MaxPositionSizeRule {
    fn name(&self) -> &'static str {
        "MaxPositionSizeRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_pos) = ctx.config.max_position_size {
            let current_pos = ctx
                .portfolio
                .positions
                .get(&order.symbol)
                .copied()
                .unwrap_or(Decimal::ZERO);
            let new_pos = match order.side {
                OrderSide::Buy => current_pos + order.quantity,
                OrderSide::Sell => current_pos - order.quantity,
            };
            if new_pos.abs() > max_pos {
                return Err(AkQuantError::OrderError(format!(
                    "Risk: Resulting position {new_pos} exceeds limit {max_pos}",
                )));
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check cash / margin sufficiency
#[derive(Debug, Clone)]
pub struct CashMarginRule;

impl RiskRule for CashMarginRule {
    fn name(&self) -> &'static str {
        "CashMarginRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if ctx.config.check_cash {
            let order_price = if let Some(p) = order.price {
                p
            } else if let Some(p) = ctx.current_prices.get(&order.symbol) {
                *p
            } else {
                return Ok(());
            };

            let mut prices_for_order = ctx.current_prices.clone();
            prices_for_order.insert(order.symbol.clone(), order_price);

            let mut projected_portfolio = ctx.portfolio.clone();
            let base_used = projected_portfolio
                .calculate_used_margin(&prices_for_order, ctx.instruments);
            {
                let positions = std::sync::Arc::make_mut(&mut projected_portfolio.positions);
                let entry = positions
                    .entry(order.symbol.clone())
                    .or_insert(Decimal::ZERO);
                match order.side {
                    OrderSide::Buy => *entry += order.quantity,
                    OrderSide::Sell => *entry -= order.quantity,
                }
            }
            let next_used = projected_portfolio
                .calculate_used_margin(&prices_for_order, ctx.instruments);
            let required_margin = (next_used - base_used).max(Decimal::ZERO);

            if required_margin.is_zero() {
                return Ok(());
            }

            let mut committed_margin = Decimal::ZERO;
            for o in ctx.active_orders {
                if o.status != crate::model::OrderStatus::New {
                    continue;
                }
                let active_price = if let Some(p) = o.price {
                    p
                } else if let Some(p) = ctx.current_prices.get(&o.symbol) {
                    *p
                } else {
                    continue;
                };
                let mut prices_for_active = ctx.current_prices.clone();
                prices_for_active.insert(o.symbol.clone(), active_price);

                let before_used = projected_portfolio
                    .calculate_used_margin(&prices_for_active, ctx.instruments);
                {
                    let positions = std::sync::Arc::make_mut(&mut projected_portfolio.positions);
                    let entry = positions.entry(o.symbol.clone()).or_insert(Decimal::ZERO);
                    match o.side {
                        OrderSide::Buy => *entry += o.quantity,
                        OrderSide::Sell => *entry -= o.quantity,
                    }
                }
                let after_used = projected_portfolio
                    .calculate_used_margin(&prices_for_active, ctx.instruments);
                committed_margin += (after_used - before_used).max(Decimal::ZERO);
            }

            let free_margin = ctx
                .portfolio
                .calculate_free_margin(ctx.current_prices, ctx.instruments);
            let safety_margin = ctx.config.safety_margin;
            let safety_factor = Decimal::from_f64(1.0 - safety_margin)
                .unwrap_or(Decimal::from_f64(0.9999).unwrap());
            let available_margin = (free_margin * safety_factor - committed_margin).max(Decimal::ZERO);

            if required_margin > available_margin {
                return Err(AkQuantError::OrderError(format!(
                    "Risk: Insufficient margin. Required: {required_margin}, Available: {available_margin} (Free: {free_margin}, Committed: {committed_margin}, Safety: {safety_margin})",
                )));
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}
