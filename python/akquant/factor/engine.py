import logging
from typing import List, Optional

import polars as pl

from ..data import ParquetDataCatalog
from .parser import ExpressionParser

logger = logging.getLogger(__name__)


class FactorEngine:
    """Engine for calculating factors using Polars Lazy API."""

    def __init__(self, catalog: ParquetDataCatalog):
        """Initialize the FactorEngine with a data catalog."""
        self.catalog = catalog
        self.parser = ExpressionParser()

    def load_data(self) -> pl.LazyFrame:
        """
        Load all data from catalog as a LazyFrame.

        Assumes data is partitioned by symbol or simply stored in separate files.
        """
        # We look for all parquet files under the root
        # Pattern: root/**/data.parquet
        # This covers:
        # - root/AAPL/data.parquet (ParquetDataCatalog default)
        # - root/symbol=AAPL/data.parquet (Hive style)
        pattern = str(self.catalog.root / "**" / "*.parquet")

        try:
            # use_pyarrow=True often helps with nested paths compatibility
            lf = pl.scan_parquet(pattern)
            return lf
        except Exception as e:
            logger.warning(f"Failed to scan parquet files: {e}")
            return pl.DataFrame().lazy()

    def run(
        self,
        expr_str: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        Execute a factor expression.

        :param expr_str: The factor expression string (e.g., "Rank(Ts_Mean(Close, 5))")
        :param start_date: Filter start date (inclusive).
        :param end_date: Filter end date (inclusive).
        :return: DataFrame with [date, symbol, factor] columns.
        """
        logger.info(f"Parsing expression: {expr_str}")
        factor_expr = self.parser.parse(expr_str)

        lf = self.load_data()

        # Filter by date if requested
        # Note: We assume the date column is named "index" or "date".
        # We need to standardize this.
        # ParquetDataCatalog stores index (datetime) usually.
        # When read by Polars, index is often a column if it was named,
        # or "__index_level_0__".
        # Let's inspect the schema or assume "date" or "index".
        # Better: let's try to coalesce "date" and "index".

        # Check columns available in lazy schema (hint)
        # We can't easily check schema without peeking.
        # But we can assume standard columns.

        # Let's standardize on "date" for our logic.
        # If "date" doesn't exist but "index" does, rename it.
        # If neither, we have a problem.

        # Robust approach:
        # 1. Rename common time columns to 'date'
        # 2. Sort by [symbol, date]
        # 3. Compute

        # But we can't do conditional rename easily in LazyFrame without schema.
        # Let's assume the user/catalog ensures 'date' or index is valid.
        # ParquetDataCatalog writes pandas DataFrame.
        # If index is named "date", it's "date".
        # If unnamed, it might be "__index_level_0__" or similar.
        # Let's assume standard columns: open, high, low, close, volume, symbol.
        # And time?

        # Let's rely on the user to have "date" column or index named "date".
        # If it's unnamed index, Polars reads it?
        # Actually, pandas `to_parquet` preserves index.
        # Polars `read_parquet` reads index as column ONLY if it has a name.
        # My `ParquetDataCatalog` sets index name to "date" if it was "date" column.

        # Sort is crucial for rolling window functions
        lf = lf.sort(["symbol", "date"])

        if start_date:
            lf = lf.filter(pl.col("date") >= pl.lit(start_date))
        if end_date:
            lf = lf.filter(pl.col("date") <= pl.lit(end_date))

        # Select and Compute
        result_lf = lf.select(
            [pl.col("date"), pl.col("symbol"), factor_expr.alias("factor_value")]
        )

        # Collect results
        logger.info("Executing query plan...")
        df = result_lf.collect()
        return df

    def run_batch(self, exprs: List[str]) -> pl.DataFrame:
        """Run multiple expressions at once."""
        lf = self.load_data().sort(["symbol", "date"])

        selections = [pl.col("date"), pl.col("symbol")]
        for i, expr_str in enumerate(exprs):
            expr = self.parser.parse(expr_str)
            selections.append(expr.alias(f"factor_{i}"))

        return lf.select(selections).collect()
