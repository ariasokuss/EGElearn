import { Slide, ToastContainer, ToastContentProps } from "react-toastify";
import { InfoCircleIcon, XMarkIcon } from "../assets/icons";
import { Button } from "./button";

export function Notifications() {
    return (
        <ToastContainer
            transition={Slide}
            hideProgressBar
            closeButton={false}
        />
    )
}

export type NotificationInfo = {
    content?: string
    header?: string
    button?: {
        buttonText: string
        onButtonClick: VoidFunction
    }
}

export function Notification({ data, closeToast }: ToastContentProps<NotificationInfo>) {
    return (
        <div className="group relative flex gap-3 items-center p-3">
            <Button 
                variant="outline"
                iconOnly
                size="xxs"
                className="absolute left-0 top-0 -translate-1/3! opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={closeToast}
            >
                <XMarkIcon className="size-4"/>
            </Button>
            
            <InfoCircleIcon className="size-6 shrink-0" />
            <div>
                {data.header && <p className="nova-text-label-base font-semibold">{data.header}</p>}
                {data.content}
            </div>

            {data.button &&
                <Button 
                    variant="outline"
                    size="xxs"
                    onClick={() => {
                        data.button!.onButtonClick()
                        setTimeout(() => closeToast(), 200)
                    }}
                    className="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                    {data.button.buttonText}
                </Button>
            }
        </div>
    )
}