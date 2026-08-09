import {
  useCallback,
  useId,
  useState,
  type PointerEvent,
  type ReactNode,
} from "react";

/**
 * The one place technical detail is allowed to live.
 *
 * A paragraph explaining how a number was derived is worth having and is not
 * worth the column inches it was taking on every page. Hover it with a mouse,
 * press and hold it on a phone, tab to it with a keyboard. It is never the
 * only route to something a reader needs, so losing it costs nothing.
 *
 * Bubbles hold text only. A link inside one would be unreachable, because
 * moving the pointer toward it closes the thing it sits in.
 */
export function InfoMarker({
  children,
  label,
}: {
  readonly children: ReactNode;
  /** What the marker explains, spoken to a screen reader: "About xPts". */
  readonly label: string;
}) {
  const bubbleId = useId();
  const [shown, setShown] = useState(false);

  // The layout is full-bleed, so a marker can sit against either edge and a
  // centred bubble would hang off the page. Nudged as it mounts, which is once
  // per opening and needs no state to survive a close.
  const keepOnScreen = useCallback((node: HTMLSpanElement | null) => {
    if (!node) return;
    const box = node.getBoundingClientRect();
    const gutter = 8;
    const spill = box.right - (window.innerWidth - gutter);
    const short = gutter - box.left;
    if (spill > 0)
      node.style.transform = `translateX(calc(-50% - ${String(Math.ceil(spill))}px))`;
    else if (short > 0)
      node.style.transform = `translateX(calc(-50% + ${String(Math.ceil(short))}px))`;
  }, []);

  // Holding is the touch gesture, so the tap must not also focus or click.
  function press(event: PointerEvent<HTMLButtonElement>) {
    if (event.pointerType !== "touch") return;
    event.preventDefault();
    setShown(true);
  }

  // Releasing only ends a hold. A mouse click must not close what hovering opened.
  function release(event: PointerEvent<HTMLButtonElement>) {
    if (event.pointerType === "touch") setShown(false);
  }

  return (
    <span className="info-marker">
      <button
        aria-describedby={shown ? bubbleId : undefined}
        aria-label={`About ${label}`}
        className="info-marker-pip"
        onBlur={() => {
          setShown(false);
        }}
        onFocus={() => {
          setShown(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setShown(false);
        }}
        onPointerCancel={release}
        onPointerDown={press}
        onPointerEnter={(event) => {
          if (event.pointerType !== "touch") setShown(true);
        }}
        onPointerLeave={() => {
          setShown(false);
        }}
        onPointerUp={release}
        type="button"
      >
        <span aria-hidden="true">i</span>
      </button>
      {shown ? (
        <span
          className="info-marker-bubble"
          id={bubbleId}
          ref={keepOnScreen}
          role="tooltip"
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
