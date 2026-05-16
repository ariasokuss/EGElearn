"use client";

import { IMaskInput } from "react-imask";

interface EmailInputProps extends Omit<React.ComponentProps<"input">, "onChange" | "value"> {
  value?: string;
  onChange?: (e: { target: { name?: string; value: string } }) => void;
}

const EMAIL_MASK = /^\S*@?\S*$/;

export function EmailInput({ onChange, ...props }: EmailInputProps) {
  return (
    <IMaskInput
      mask={EMAIL_MASK}
      unmask={true}
      onAccept={(value) => {
        onChange?.({ target: { name: props.name, value: value ?? "" } });
      }}
      type="email"
      inputMode="email"
      autoComplete="email"
      placeholder="example@mail.com"
      {...props}
    />
  );
}
