/**
 * Modal: dialog semantics, Escape/backdrop dismissal, and focus handling
 * (focus moves into the panel, is trapped by Tab, and is restored on close).
 */

import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Modal } from "@/components/Modal";

function Body() {
  return (
    <>
      <input placeholder="First field" />
      <button type="button">Confirm</button>
    </>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        titleId="harness-title"
        title="Harness Dialog"
      >
        <Body />
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("renders nothing while closed", () => {
    render(
      <Modal open={false} onClose={vi.fn()} titleId="t" title="Hidden">
        <Body />
      </Modal>
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a labelled modal dialog when open", () => {
    render(
      <Modal open onClose={vi.fn()} titleId="t" title="Harness Dialog">
        <Body />
      </Modal>
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Harness Dialog");
  });

  it("closes on Escape", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes on a backdrop click but not on a panel click", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));

    fireEvent.click(screen.getByRole("dialog"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("dialog").parentElement!);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes from the Close button", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("moves focus to the first focusable element and restores it on close", async () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);

    await waitFor(() => expect(screen.getByPlaceholderText("First field")).toHaveFocus());

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("wraps Tab and Shift+Tab inside the panel", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(screen.getByPlaceholderText("First field")).toHaveFocus());

    const first = screen.getByPlaceholderText("First field");
    const close = screen.getByRole("button", { name: "Close" });

    // Shift+Tab from the first element wraps to the last (the Close button).
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(close).toHaveFocus();

    // Tab from the last element wraps back to the first.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();
  });
});
