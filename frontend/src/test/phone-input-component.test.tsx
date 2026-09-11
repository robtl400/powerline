/**
 * Component render tests for PhoneInput.
 * Tests blur-based validation behavior, prefix rendering, and error display.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PhoneInput } from "@/components/PhoneInput";

function renderPhoneInput(value = "", onChange = vi.fn()) {
  return render(<PhoneInput value={value} onChange={onChange} />);
}

describe("PhoneInput — rendering", () => {
  it("renders the +1 prefix", () => {
    renderPhoneInput();
    expect(screen.getByText(/\+1/)).toBeInTheDocument();
  });

  it("renders the input element", () => {
    renderPhoneInput();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("shows formatted display value from E.164 prop", () => {
    renderPhoneInput("+12025551234");
    expect(screen.getByRole("textbox")).toHaveValue("(202) 555-1234");
  });

  it("shows empty display for empty value", () => {
    renderPhoneInput("");
    expect(screen.getByRole("textbox")).toHaveValue("");
  });
});

describe("PhoneInput — blur-based validation", () => {
  it("does not show error before the field is touched", () => {
    // Simulate a partial value (+12) which would be invalid
    renderPhoneInput("+12");
    expect(screen.queryByText(/10-digit/)).not.toBeInTheDocument();
  });

  it("shows error after blur with incomplete number", () => {
    renderPhoneInput("+12");
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);
    expect(screen.getByText(/10-digit US phone number/)).toBeInTheDocument();
  });

  it("does not show error after blur with valid 10-digit number", () => {
    renderPhoneInput("+12025551234");
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);
    expect(screen.queryByText(/10-digit/)).not.toBeInTheDocument();
  });

  it("does not show error when value is empty after blur", () => {
    renderPhoneInput("");
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);
    expect(screen.queryByText(/10-digit/)).not.toBeInTheDocument();
  });

  it("clears error appearance when user completes the number after blur", () => {
    const { rerender } = render(<PhoneInput value="+12" onChange={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);
    expect(screen.getByText(/10-digit/)).toBeInTheDocument();

    // Parent updates value to valid number
    rerender(<PhoneInput value="+12025551234" onChange={vi.fn()} />);
    expect(screen.queryByText(/10-digit/)).not.toBeInTheDocument();
  });
});

describe("PhoneInput — error wiring", () => {
  it("carries no aria-invalid or description while valid", () => {
    renderPhoneInput("+12025551234");
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);

    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
  });

  it("marks the field invalid and points it at the alert message", () => {
    renderPhoneInput("+12");
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/10-digit US phone number/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", alert.id);
    expect(alert.id).not.toBe("");
  });

  it("gives each instance its own error id", () => {
    render(
      <>
        <PhoneInput value="+12" onChange={vi.fn()} />
        <PhoneInput value="+13" onChange={vi.fn()} />
      </>
    );
    const [first, second] = screen.getAllByRole("textbox");
    fireEvent.blur(first);
    fireEvent.blur(second);

    const [firstAlert, secondAlert] = screen.getAllByRole("alert");
    expect(firstAlert.id).not.toBe(secondAlert.id);
    expect(first).toHaveAttribute("aria-describedby", firstAlert.id);
    expect(second).toHaveAttribute("aria-describedby", secondAlert.id);
  });
});

describe("PhoneInput — onChange", () => {
  it("calls onChange with E.164 when user types digits", () => {
    const onChange = vi.fn();
    render(<PhoneInput value="" onChange={onChange} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "2025551234" } });
    expect(onChange).toHaveBeenCalledWith("+12025551234");
  });

  it("strips non-digits from typed input", () => {
    const onChange = vi.fn();
    render(<PhoneInput value="" onChange={onChange} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "(202) 555-1234" } });
    expect(onChange).toHaveBeenCalledWith("+12025551234");
  });
});
