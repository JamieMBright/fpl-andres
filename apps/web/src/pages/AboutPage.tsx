import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

type ContactState = "idle" | "sending" | "sent" | "failed";

export default function AboutPage() {
  useDocumentTitle(
    "About",
    "What FPL Andres does, why the evidence stays visible, and how to get in touch.",
    { canonicalPath: "/about" },
  );

  const [state, setState] = useState<ContactState>("idle");
  const [error, setError] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const email = String(values.get("email") ?? "").trim();
    const message = String(values.get("message") ?? "").trim();

    if (!emailRef.current?.validity.valid) {
      setError("Enter a valid reply email.");
      emailRef.current?.focus();
      return;
    }
    if (message.length < 20) {
      setError("Write at least 20 characters so I have enough to answer.");
      messageRef.current?.focus();
      return;
    }

    setError(null);
    setState("sending");
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          submissionId: crypto.randomUUID(),
          email,
          message,
          website: String(values.get("website") ?? ""),
        }),
      });
      if (!response.ok) throw new Error("contact unavailable");
      form.reset();
      setState("sent");
    } catch {
      setState("failed");
      setError("The message did not send. Keep it here and try again shortly.");
    }
  };

  return (
    <section className="text-page about-page">
      <p className="eyebrow">About</p>
      <RouteHeading>About FPL Andres</RouteHeading>

      <div className="about-ledger">
        <section aria-labelledby="about-what">
          <p className="about-ledger-number" aria-hidden="true">
            01
          </p>
          <div>
            <h2 id="about-what">What I do</h2>
            <p>
              I turn public Fantasy Premier League data into next-deadline
              calls, player comparisons and a season plan built from your
              fifteen.
            </p>
            <p>
              Every recommendation keeps its evidence, timestamp and uncertainty
              attached. Read the <Link to="/methodology">method</Link> or
              inspect the <Link to="/calibration">scorecard</Link> when the
              number matters.
            </p>
          </div>
        </section>

        <section aria-labelledby="about-why">
          <p className="about-ledger-number" aria-hidden="true">
            02
          </p>
          <div>
            <h2 id="about-why">Why I do it</h2>
            <p>
              Deadline decisions get noisy. I want the useful number first, the
              working directly underneath it, and a visible refusal when the
              source cannot support an answer.
            </p>
            <p>All forecasts are wrong. Some are useful.</p>
          </div>
        </section>

        <section aria-labelledby="about-origin">
          <p className="about-ledger-number" aria-hidden="true">
            03
          </p>
          <div>
            <h2 id="about-origin">Where Andres comes from</h2>
            <p>
              Andres is the fictional analyst behind the dossier: pulled into a
              Bielsa-era spotlight because he spoke Spanish, aware that luck
              opened the door, and determined to repay it with work good enough
              to survive scrutiny.
            </p>
            <p>
              That is the voice of the product, not a biography or a claim of
              club affiliation.
            </p>
          </div>
        </section>

        <section aria-labelledby="about-contact">
          <p className="about-ledger-number" aria-hidden="true">
            04
          </p>
          <div>
            <h2 id="about-contact">Contact</h2>
            <p>
              Send a question, correction or collaboration note. Your reply
              address and message go only to the mail provider and the private
              project inbox; they are not added to a mailing list or stored in
              the analysis database.
            </p>
            <form className="contact-form" noValidate onSubmit={submit}>
              <div className="contact-field">
                <label htmlFor="contact-email">Your email</label>
                <input
                  ref={emailRef}
                  aria-invalid={error?.includes("email") || undefined}
                  autoComplete="email"
                  id="contact-email"
                  maxLength={254}
                  name="email"
                  required
                  spellCheck={false}
                  type="email"
                />
              </div>
              <div className="contact-field contact-field-message">
                <label htmlFor="contact-message">Message</label>
                <textarea
                  ref={messageRef}
                  aria-invalid={error?.includes("20 characters") || undefined}
                  id="contact-message"
                  maxLength={4000}
                  minLength={20}
                  name="message"
                  required
                  rows={7}
                />
                <span>20–4,000 characters</span>
              </div>
              <div className="contact-honeypot" hidden>
                <label htmlFor="contact-website">Website</label>
                <input
                  autoComplete="off"
                  id="contact-website"
                  name="website"
                  tabIndex={-1}
                  type="text"
                />
              </div>
              <button disabled={state === "sending"} type="submit">
                {state === "sending" ? "Sending…" : "Send message"}
              </button>
              <p aria-live="polite" className="contact-status">
                {state === "sent"
                  ? "Message sent. I will reply by email."
                  : error}
              </p>
            </form>
            <p className="contact-privacy">
              Read the full <Link to="/privacy">privacy note</Link> before
              sending anything sensitive.
            </p>
          </div>
        </section>
      </div>
    </section>
  );
}
