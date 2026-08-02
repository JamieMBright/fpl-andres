import { WifiOff } from "lucide-react";

import { useOnlineStatus } from "../state/use-online-status";

/**
 * Audit item #120. A dropped connection reached the page as "Fantasy Premier
 * League could not be reached", which sends someone to check the wrong thing.
 *
 * The banner is a status region rather than an alert: losing a connection is
 * worth announcing once, but it is not an error that interrupts what someone
 * was doing, and `role="alert"` on a laptop lid closing and reopening would
 * interrupt a screen reader repeatedly for no gain.
 *
 * It says what is still usable, because most of this site is. Last season's
 * record, the opening squad and the method pages are all built into the bundle
 * and need no network at all -- only the live team lookup does.
 */
export function OfflineBanner() {
  const online = useOnlineStatus();
  if (online) return null;

  return (
    <div className="offline-banner" role="status" aria-live="polite">
      <WifiOff aria-hidden="true" size={16} />
      <p>
        <strong>No connection.</strong> Player records, the opening squad and
        the method pages still work. Looking up a live team needs the network.
      </p>
    </div>
  );
}
