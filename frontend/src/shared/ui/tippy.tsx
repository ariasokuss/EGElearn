"use client"

import TippyJs, { type TippyProps } from "@tippyjs/react"
import { useRef, type RefObject } from "react"

export function Tippy(props: TippyProps) {
    const { children, reference, ...rest } = props
    const fallbackRef = useRef<HTMLDivElement>(null)

    if (children != null && reference == null) {
        return (
            <>
                <div ref={fallbackRef} className="inline-flex">
                    {children}
                </div>
                <TippyJs
                    {...rest}
                    reference={fallbackRef as RefObject<Element>}
                />
            </>
        )
    }

    return <TippyJs {...props} />
}
