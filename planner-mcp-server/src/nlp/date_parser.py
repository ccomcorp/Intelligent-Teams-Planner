"""
Natural Language Date Parsing
Story 1.3 Task 2: Support for relative date expressions
"""

import re
import asyncio
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta
import calendar
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ParsedDate:
    """Result of date parsing"""
    date: datetime
    confidence: float
    original_text: str
    date_type: str  # 'absolute', 'relative', 'range'
    end_date: Optional[datetime] = None  # For date ranges


@dataclass
class DateParsingResult:
    """Complete result of date parsing operation"""
    parsed_dates: List[ParsedDate]
    unparsed_text: str
    metadata: Dict[str, any]


class DateParser:
    """
    Natural language date parser with support for relative expressions
    Handles timezone awareness and business rules
    """

    def __init__(self, default_timezone: str = "UTC", business_hours_start: int = 9, business_hours_end: int = 17):
        self.default_timezone = timezone.utc if default_timezone == "UTC" else timezone.utc  # Simplified for now
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end
        self.working_days = [0, 1, 2, 3, 4]  # Monday-Friday

        # Define relative date patterns and their handlers
        self.relative_patterns = {
            # Today/Tomorrow/Yesterday
            r'\b(today)\b': self._parse_today,
            r'\b(tomorrow)\b': self._parse_tomorrow,
            r'\b(yesterday)\b': self._parse_yesterday,

            # This/Next/Last + time period
            r'\b(this|next|last)\s+(week|month|year|quarter)\b': self._parse_period_relative,
            r'\b(this|next|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b': self._parse_weekday_relative,

            # In X time units
            r'\bin\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)\b': self._parse_in_duration,
            r'\bin\s+a\s+(day|week|month|year)\b': self._parse_in_duration_article,

            # X time units ago
            r'\b(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+ago\b': self._parse_duration_ago,
            r'\ba\s+(day|week|month|year)\s+ago\b': self._parse_duration_ago_article,

            # End of/Beginning of
            r'\b(end|beginning|start)\s+of\s+(this|next|last)\s+(week|month|year|quarter)\b': self._parse_period_boundary,
            r'\b(end|beginning|start)\s+of\s+(week|month|year|quarter)\b': self._parse_period_boundary_current,

            # Business day expressions
            r'\b(next|last)\s+business\s+day\b': self._parse_business_day,
            r'\b(next|last)\s+working\s+day\b': self._parse_business_day,

            # Week expressions
            r'\b(this|next|last)\s+week\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b': self._parse_week_day,

            # Date ranges
            r'\b(this|next|last)\s+week\b': self._parse_week_range,
            r'\b(this|next|last)\s+month\b': self._parse_month_range,
        }

        # Absolute date patterns
        self.absolute_patterns = [
            r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\b',  # MM/DD/YYYY or DD/MM/YYYY
            r'\b(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\b',    # YYYY/MM/DD
            r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s+(\d{4}))?\b',
            r'\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\b',
        ]

        # Day name mappings
        self.day_names = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        # Month name mappings
        self.month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

    async def parse_dates(self, text: str, reference_date: Optional[datetime] = None) -> DateParsingResult:
        """
        Parse natural language date expressions from text

        Args:
            text: Input text containing date expressions
            reference_date: Reference date for relative calculations (defaults to now)

        Returns:
            DateParsingResult with parsed dates and metadata
        """
        try:
            if reference_date is None:
                reference_date = datetime.now(self.default_timezone)

            parsed_dates = []
            remaining_text = text.lower()
            metadata = {
                "reference_date": reference_date.isoformat(),
                "patterns_matched": [],
                "confidence_scores": []
            }

            # First, try relative date patterns
            relative_dates, remaining_text = await self._parse_relative_dates(remaining_text, reference_date)
            parsed_dates.extend(relative_dates)

            # Then, try absolute date patterns
            absolute_dates, remaining_text = await self._parse_absolute_dates(remaining_text, reference_date)
            parsed_dates.extend(absolute_dates)

            # Finally, try dateutil parser for any remaining date-like strings
            fallback_dates, remaining_text = await self._parse_with_dateutil(remaining_text, reference_date)
            parsed_dates.extend(fallback_dates)

            # Remove duplicates and sort by confidence
            parsed_dates = self._deduplicate_dates(parsed_dates)
            parsed_dates.sort(key=lambda d: d.confidence, reverse=True)

            # Validate parsed dates against business rules
            parsed_dates = self._validate_dates(parsed_dates, reference_date)

            metadata.update({
                "total_dates_found": len(parsed_dates),
                "average_confidence": sum(d.confidence for d in parsed_dates) / len(parsed_dates) if parsed_dates else 0
            })

            logger.debug("Date parsing completed",
                        num_dates=len(parsed_dates),
                        original_text=text[:100])

            return DateParsingResult(
                parsed_dates=parsed_dates,
                unparsed_text=remaining_text.strip(),
                metadata=metadata
            )

        except Exception as e:
            logger.error("Error parsing dates", error=str(e), text=text[:100])
            return DateParsingResult(
                parsed_dates=[],
                unparsed_text=text,
                metadata={"error": str(e)}
            )

    async def _parse_relative_dates(self, text: str, reference_date: datetime) -> Tuple[List[ParsedDate], str]:
        """Parse relative date expressions"""
        parsed_dates = []
        remaining_text = text

        for pattern, handler in self.relative_patterns.items():
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                try:
                    parsed_date = await handler(match, reference_date)
                    if parsed_date:
                        parsed_dates.append(parsed_date)
                        # Remove the matched text
                        remaining_text = remaining_text.replace(match.group(0), '', 1)
                except Exception as e:
                    logger.warning("Error parsing relative date", error=str(e), match=match.group(0))

        return parsed_dates, remaining_text

    async def _parse_absolute_dates(self, text: str, reference_date: datetime) -> Tuple[List[ParsedDate], str]:
        """Parse absolute date expressions"""
        parsed_dates = []
        remaining_text = text

        for pattern in self.absolute_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                try:
                    parsed_date = await self._parse_absolute_date_match(match, reference_date)
                    if parsed_date:
                        parsed_dates.append(parsed_date)
                        # Remove the matched text
                        remaining_text = remaining_text.replace(match.group(0), '', 1)
                except Exception as e:
                    logger.warning("Error parsing absolute date", error=str(e), match=match.group(0))

        return parsed_dates, remaining_text

    async def _parse_with_dateutil(self, text: str, reference_date: datetime) -> Tuple[List[ParsedDate], str]:
        """Parse remaining date expressions using dateutil"""
        parsed_dates = []
        remaining_text = text

        # Look for potential date strings
        potential_dates = re.findall(r'\b\w+\s+\d{1,2}(?:st|nd|rd|th)?\b', text)

        for date_str in potential_dates:
            try:
                loop = asyncio.get_event_loop()
                parsed_dt = await loop.run_in_executor(
                    None,
                    lambda: dateutil_parser.parse(date_str, default=reference_date)
                )

                parsed_date = ParsedDate(
                    date=parsed_dt.replace(tzinfo=self.default_timezone),
                    confidence=0.6,  # Lower confidence for dateutil fallback
                    original_text=date_str,
                    date_type='absolute'
                )
                parsed_dates.append(parsed_date)
                remaining_text = remaining_text.replace(date_str, '', 1)

            except Exception:
                # dateutil couldn't parse it, skip
                continue

        return parsed_dates, remaining_text

    # Relative date parsing handlers

    async def _parse_today(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'today'"""
        today = reference_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
        return ParsedDate(
            date=today,
            confidence=0.95,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_tomorrow(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'tomorrow'"""
        tomorrow = reference_date + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
        return ParsedDate(
            date=tomorrow,
            confidence=0.95,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_yesterday(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'yesterday'"""
        yesterday = reference_date - timedelta(days=1)
        yesterday = yesterday.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
        return ParsedDate(
            date=yesterday,
            confidence=0.95,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_period_relative(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'this/next/last week/month/year/quarter'"""
        direction = match.group(1).lower()  # this/next/last
        period = match.group(2).lower()     # week/month/year/quarter

        if period == 'week':
            if direction == 'this':
                # Start of current week (Monday)
                days_since_monday = reference_date.weekday()
                start_of_week = reference_date - timedelta(days=days_since_monday)
            elif direction == 'next':
                days_since_monday = reference_date.weekday()
                start_of_week = reference_date + timedelta(days=7 - days_since_monday)
            else:  # last
                days_since_monday = reference_date.weekday()
                start_of_week = reference_date - timedelta(days=days_since_monday + 7)

            target_date = start_of_week.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        elif period == 'month':
            if direction == 'this':
                target_date = reference_date.replace(day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            elif direction == 'next':
                if reference_date.month == 12:
                    target_date = reference_date.replace(year=reference_date.year + 1, month=1, day=1)
                else:
                    target_date = reference_date.replace(month=reference_date.month + 1, day=1)
                target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            else:  # last
                if reference_date.month == 1:
                    target_date = reference_date.replace(year=reference_date.year - 1, month=12, day=1)
                else:
                    target_date = reference_date.replace(month=reference_date.month - 1, day=1)
                target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        elif period == 'year':
            if direction == 'this':
                target_date = reference_date.replace(month=1, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            elif direction == 'next':
                target_date = reference_date.replace(year=reference_date.year + 1, month=1, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            else:  # last
                target_date = reference_date.replace(year=reference_date.year - 1, month=1, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        elif period == 'quarter':
            current_quarter = (reference_date.month - 1) // 3 + 1
            if direction == 'this':
                quarter_start_month = (current_quarter - 1) * 3 + 1
                target_date = reference_date.replace(month=quarter_start_month, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            elif direction == 'next':
                next_quarter = current_quarter + 1 if current_quarter < 4 else 1
                year_offset = 0 if current_quarter < 4 else 1
                quarter_start_month = (next_quarter - 1) * 3 + 1
                target_date = reference_date.replace(year=reference_date.year + year_offset, month=quarter_start_month, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)
            else:  # last
                last_quarter = current_quarter - 1 if current_quarter > 1 else 4
                year_offset = 0 if current_quarter > 1 else -1
                quarter_start_month = (last_quarter - 1) * 3 + 1
                target_date = reference_date.replace(year=reference_date.year + year_offset, month=quarter_start_month, day=1, hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        else:
            raise ValueError(f"Unknown period: {period}")

        return ParsedDate(
            date=target_date,
            confidence=0.85,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_weekday_relative(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'this/next/last Monday/Tuesday/etc.'"""
        direction = match.group(1).lower()
        weekday_name = match.group(2).lower()
        target_weekday = self.day_names[weekday_name]

        current_weekday = reference_date.weekday()

        if direction == 'this':
            if target_weekday >= current_weekday:
                days_ahead = target_weekday - current_weekday
            else:
                days_ahead = target_weekday + 7 - current_weekday
        elif direction == 'next':
            days_ahead = (target_weekday - current_weekday + 7) % 7
            if days_ahead == 0:  # If it's the same day, go to next week
                days_ahead = 7
        else:  # last
            days_back = (current_weekday - target_weekday) % 7
            if days_back == 0:  # If it's the same day, go to last week
                days_back = 7
            days_ahead = -days_back

        target_date = reference_date + timedelta(days=days_ahead)
        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.9,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_in_duration(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'in X days/weeks/months/years'"""
        amount = int(match.group(1))
        unit = match.group(2).lower().rstrip('s')  # Remove plural 's'

        if unit == 'day':
            target_date = reference_date + timedelta(days=amount)
        elif unit == 'week':
            target_date = reference_date + timedelta(weeks=amount)
        elif unit == 'month':
            target_date = reference_date + relativedelta(months=amount)
        elif unit == 'year':
            target_date = reference_date + relativedelta(years=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.85,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_in_duration_article(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'in a day/week/month/year'"""
        unit = match.group(1).lower()

        if unit == 'day':
            target_date = reference_date + timedelta(days=1)
        elif unit == 'week':
            target_date = reference_date + timedelta(weeks=1)
        elif unit == 'month':
            target_date = reference_date + relativedelta(months=1)
        elif unit == 'year':
            target_date = reference_date + relativedelta(years=1)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.8,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_duration_ago(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'X days/weeks/months/years ago'"""
        amount = int(match.group(1))
        unit = match.group(2).lower().rstrip('s')

        if unit == 'day':
            target_date = reference_date - timedelta(days=amount)
        elif unit == 'week':
            target_date = reference_date - timedelta(weeks=amount)
        elif unit == 'month':
            target_date = reference_date - relativedelta(months=amount)
        elif unit == 'year':
            target_date = reference_date - relativedelta(years=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.85,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_duration_ago_article(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'a day/week/month/year ago'"""
        unit = match.group(1).lower()

        if unit == 'day':
            target_date = reference_date - timedelta(days=1)
        elif unit == 'week':
            target_date = reference_date - timedelta(weeks=1)
        elif unit == 'month':
            target_date = reference_date - relativedelta(months=1)
        elif unit == 'year':
            target_date = reference_date - relativedelta(years=1)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.8,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_period_boundary(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'end/beginning of this/next/last week/month/year/quarter'"""
        # Simplified implementation - would need more complex logic for full support
        return await self._parse_period_relative(
            re.match(r'(this|next|last)\s+(week|month|year|quarter)', match.group(0)),
            reference_date
        )

    async def _parse_period_boundary_current(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'end/beginning of week/month/year/quarter'"""
        # Simplified implementation
        return await self._parse_today(match, reference_date)

    async def _parse_business_day(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'next/last business day'"""
        direction = match.group(1).lower()

        if direction == 'next':
            target_date = reference_date + timedelta(days=1)
            while target_date.weekday() not in self.working_days:
                target_date += timedelta(days=1)
        else:  # last
            target_date = reference_date - timedelta(days=1)
            while target_date.weekday() not in self.working_days:
                target_date -= timedelta(days=1)

        target_date = target_date.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=target_date,
            confidence=0.9,
            original_text=match.group(0),
            date_type='relative'
        )

    async def _parse_week_day(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'this/next/last week Monday/Tuesday/etc.'"""
        # Simplified - would delegate to more specific handlers
        return await self._parse_weekday_relative(match, reference_date)

    async def _parse_week_range(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'this/next/last week' as a range"""
        direction = match.group(1).lower()

        # Calculate start of week (Monday)
        if direction == 'this':
            days_since_monday = reference_date.weekday()
            start_of_week = reference_date - timedelta(days=days_since_monday)
        elif direction == 'next':
            days_since_monday = reference_date.weekday()
            start_of_week = reference_date + timedelta(days=7 - days_since_monday)
        else:  # last
            days_since_monday = reference_date.weekday()
            start_of_week = reference_date - timedelta(days=days_since_monday + 7)

        end_of_week = start_of_week + timedelta(days=6)

        start_of_week = start_of_week.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
        end_of_week = end_of_week.replace(hour=self.business_hours_end, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=start_of_week,
            end_date=end_of_week,
            confidence=0.85,
            original_text=match.group(0),
            date_type='range'
        )

    async def _parse_month_range(self, match: re.Match, reference_date: datetime) -> ParsedDate:
        """Parse 'this/next/last month' as a range"""
        direction = match.group(1).lower()

        if direction == 'this':
            start_of_month = reference_date.replace(day=1)
            end_of_month = reference_date.replace(day=calendar.monthrange(reference_date.year, reference_date.month)[1])
        elif direction == 'next':
            if reference_date.month == 12:
                start_of_month = reference_date.replace(year=reference_date.year + 1, month=1, day=1)
                end_of_month = reference_date.replace(year=reference_date.year + 1, month=1, day=31)
            else:
                next_month = reference_date.month + 1
                start_of_month = reference_date.replace(month=next_month, day=1)
                end_of_month = reference_date.replace(month=next_month, day=calendar.monthrange(reference_date.year, next_month)[1])
        else:  # last
            if reference_date.month == 1:
                start_of_month = reference_date.replace(year=reference_date.year - 1, month=12, day=1)
                end_of_month = reference_date.replace(year=reference_date.year - 1, month=12, day=31)
            else:
                last_month = reference_date.month - 1
                start_of_month = reference_date.replace(month=last_month, day=1)
                end_of_month = reference_date.replace(month=last_month, day=calendar.monthrange(reference_date.year, last_month)[1])

        start_of_month = start_of_month.replace(hour=self.business_hours_start, minute=0, second=0, microsecond=0)
        end_of_month = end_of_month.replace(hour=self.business_hours_end, minute=0, second=0, microsecond=0)

        return ParsedDate(
            date=start_of_month,
            end_date=end_of_month,
            confidence=0.85,
            original_text=match.group(0),
            date_type='range'
        )

    async def _parse_absolute_date_match(self, match: re.Match, reference_date: datetime) -> Optional[ParsedDate]:
        """Parse absolute date from regex match"""
        try:
            groups = match.groups()
            date_str = match.group(0)

            # Try to parse with dateutil
            loop = asyncio.get_event_loop()
            parsed_dt = await loop.run_in_executor(
                None,
                lambda: dateutil_parser.parse(date_str, default=reference_date)
            )

            # Ensure timezone
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=self.default_timezone)

            return ParsedDate(
                date=parsed_dt,
                confidence=0.9,
                original_text=date_str,
                date_type='absolute'
            )

        except Exception as e:
            logger.debug("Failed to parse absolute date", error=str(e), match=match.group(0))
            return None

    def _deduplicate_dates(self, dates: List[ParsedDate]) -> List[ParsedDate]:
        """Remove duplicate dates, keeping the highest confidence ones"""
        if not dates:
            return dates

        # Group by date (ignoring time)
        date_groups = {}
        for parsed_date in dates:
            date_key = parsed_date.date.date()
            if date_key not in date_groups:
                date_groups[date_key] = []
            date_groups[date_key].append(parsed_date)

        # Keep the highest confidence date for each date
        deduplicated = []
        for date_key, group in date_groups.items():
            best_date = max(group, key=lambda d: d.confidence)
            deduplicated.append(best_date)

        return deduplicated

    def _validate_dates(self, dates: List[ParsedDate], reference_date: datetime) -> List[ParsedDate]:
        """Validate parsed dates against business rules"""
        validated = []

        for parsed_date in dates:
            # Check if date is reasonable (not too far in past/future)
            days_diff = abs((parsed_date.date - reference_date).days)

            if days_diff > 365 * 10:  # More than 10 years
                parsed_date.confidence *= 0.5  # Reduce confidence

            # Add business day adjustment for work-related tasks
            if parsed_date.date.weekday() not in self.working_days:
                # Slightly reduce confidence for non-business days
                parsed_date.confidence *= 0.9

            validated.append(parsed_date)

        return validated

    def format_date_for_display(self, parsed_date: ParsedDate) -> str:
        """Format a parsed date for user-friendly display"""
        if parsed_date.date_type == 'range' and parsed_date.end_date:
            return f"{parsed_date.date.strftime('%Y-%m-%d')} to {parsed_date.end_date.strftime('%Y-%m-%d')}"
        else:
            return parsed_date.date.strftime('%Y-%m-%d %H:%M %Z')

    def get_business_day_adjustment(self, date: datetime) -> datetime:
        """Adjust date to next business day if it falls on weekend"""
        while date.weekday() not in self.working_days:
            date += timedelta(days=1)
        return date