import { toast } from "react-toastify";
import { Notification, NotificationInfo } from "../ui/notifications";

export function notify(data: NotificationInfo = {}) {
    toast(Notification, {data: data})
}