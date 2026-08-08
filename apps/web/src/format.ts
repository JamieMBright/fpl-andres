/**
 * Shared number and date formatting.
 *
 * Five identical `moneyFormatter` definitions lived in five
 * components. They agreed, which is the point: five copies is five chances for
 * one to gain a decimal place and render a price differently on one page.
 *
 * Constructing an `Intl` formatter is not free, and these are built once at
 * module scope rather than per render, but the reason to share them is
 * consistency rather than speed.
 *
 * The timezone split is deliberate and was previously accidental. Anything
 * describing *when something happened in football* is London time, because FPL
 * deadlines are, and a fixture at 20:00 on Saturday is not a fixture at 19:00.
 * Anything describing *when data was captured* stays UTC, because that is what
 * the provenance record stores and re-rendering it in local time would make two
 * snapshots taken a minute apart appear on different days.
 */

export const money = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export const integer = new Intl.NumberFormat("en-GB");

/** When something happened in football. */
export const timestamp = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/London",
  timeZoneName: "short",
});

/**
 * An FPL deadline.
 *
 * London, not UTC. Deadlines are stored as UTC instants and FPL publishes them
 * in UK time, so rendering the instant as UTC labels 17:30Z as "17:30" when the
 * deadline a UK user must actually meet is 18:30 BST. An hour wrong, in the one
 * place on the site where being an hour wrong costs points.
 */
export const deadline = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "Europe/London",
});

/** When data was captured. UTC, matching the provenance record. */
export const captureDay = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

/**
 * A deadline reduced to a date, for the season plan rail where thirty-eight of
 * them appear at once. UK time for the same reason the full formatter uses it.
 */
export const deadlineDay = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "Europe/London",
});

/** A point total to a tenth: minutes, rates, anything read at a glance. */
export const oneDecimal = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/**
 * A point total to a hundredth, for a difference small enough to need it.
 *
 * Trailing zeroes are kept: an interval printed as "-0.34 to +0.6" reads as
 * less precise on one end than the other when both were measured the same way.
 */
export const twoDecimals = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
