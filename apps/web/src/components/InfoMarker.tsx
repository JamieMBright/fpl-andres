import {
  useCallback,
  useId,
  useRef,
  useState,
  type PointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

/**
 * The one place technical detail is allowed to live.
 *
 * A paragraph explaining how a number was derived is worth having and is not
 * worth the column inches it was taking on every page. Hover it with a mouse,
 * press and hold it on a phone, tab to it with a keyboard. It is never the
 * only route to something a reader needs, so losing it costs nothing.
 *
 * The bubble is portalled to the document and positioned against the viewport.
 * Absolute positioning meant any scrolling ancestor clipped it, so a marker
 * inside a sidebar opened its explanation where nobody could read it -- and
 * the alternative was a sidebar that could not scroll.
 *
 * Bubbles hold text only. A link inside one would be unreachable, because
 * moving the pointer toward it closes the thing it sits in.
 */

/** Distance from the pip, and the smallest gap allowed to the window edge. */
const OFFSET = 8;

export function InfoMarker({
  children,
  label,
}: {
  readonly children: ReactNode;
  /** What the marker explains, spoken to a screen reader: "About xPts". */
  readonly label: string;
}) {
  const bubbleId = useId();
  const pip = useRef<HTMLButtonElement>(null);
  const [spot, setSpot] = useState<{ left: number; top: number } | null>(null);

  function open() {
    const box = pip.current?.getBoundingClientRect();
    if (!box) return;
    setSpot({ left: box.left + box.width / 2, top: box.top - OFFSET });
  }

  // Measured after it mounts, because its width is not known before then.
  const keepOnScreen = useCallback((node: HTMLSpanElement | null) => {
    if (!node) return;
    const box = node.getBoundingClientRect();
    const spill = box.right - (window.innerWidth - OFFSET);
    const short = OFFSET - box.left;
    if (spill > 0) node.style.marginLeft = `${String(-Math.ceil(spill))}px`;
    else if (short > 0) node.style.marginLeft = `${String(Math.ceil(short))}px`;
    // Nothing above it to open into, so it drops below the pip instead.
    if (box.top < OFFSET) {
      node.style.transform = "translate(-50%, 0)";
      node.style.marginTop = `${String(box.height + OFFSET * 2)}px`;
    }
  }, []);

  // Holding is the touch gesture, so the tap must not also focus or click.
  function press(event: PointerEvent<HTMLButtonElement>) {
    if (event.pointerType !== "touch") return;
    event.preventDefault();
    open();
  }

  // Releasing only ends a hold. A mouse click must not close what hovering opened.
  function release(event: PointerEvent<HTMLButtonElement>) {
    if (event.pointerType === "touch") setSpot(null);
  }

  return (
    <span className="info-marker">
      <button
        aria-describedby={spot ? bubbleId : undefined}
        aria-label={`About ${label}`}
        className="info-marker-pip"
        onBlur={() => {
          setSpot(null);
        }}
        onFocus={open}
        onKeyDown={(event) => {
          if (event.key === "Escape") setSpot(null);
        }}
        onPointerCancel={release}
        onPointerDown={press}
        onPointerEnter={(event) => {
          if (event.pointerType !== "touch") open();
        }}
        onPointerLeave={() => {
          setSpot(null);
        }}
        onPointerUp={release}
        ref={pip}
        type="button"
      >
        <span aria-hidden="true">i</span>
      </button>
      {spot
        ? createPortal(
            <span
              className="info-marker-bubble"
              id={bubbleId}
              ref={keepOnScreen}
              role="tooltip"
              style={{ left: spot.left, top: spot.top }}
            >
              {children}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
