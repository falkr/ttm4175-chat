from dearpygui.core import *
from dearpygui.simple import *
import uuid
import time


SEND_STATUS_READ = "read"
SEND_STATUS_DELIVERED = "delivered"

RECEIVE_STATUS_READ = "read"


class Message:
    def __init__(
        self,
        sender: str,
        receiver: str,
        message: str,
        message_uuid: str,
        sent_by_me: bool,
    ):
        self.sender = sender
        self.message = message
        self.receiver = receiver
        self.uuid = message_uuid
        self.send_status = None
        self.receive_status = None
        self.sent_by_me = sent_by_me

    def _get_string(self):
        if self.send_status:
            return (
                self.sender + ":\n  " + self.message + "\n (" + self.send_status + ")"
            )
        else:
            return self.sender + ":\n  " + self.message

    def set_send_status(self, send_status):
        self.send_status = send_status

    def is_sent_by_me(self):
        return self.sent_by_me

    def is_read(self):
        return self.receive_status == RECEIVE_STATUS_READ

    def mark_as_read(self):
        self.receive_status = RECEIVE_STATUS_READ

    @staticmethod
    def create_message(sender, receiver, message):
        return Message(sender, receiver, message, uuid.uuid4().hex, True)


class History:
    def __init__(self, contact):
        self.contact = contact
        self.messages = []
        self.messages_by_uuid = {}
        self.typing = False

    def add_message(self, message):
        self.messages.append(message)
        self.messages_by_uuid[message.uuid] = message

    def set_message_status(self, message_uuid, status):
        if message_uuid in self.messages_by_uuid:
            self.messages_by_uuid[message_uuid].set_status(status)

    def _get_rows(self):
        return [[message._get_string()] for message in self.messages]

    def set_typing(self, typing):
        self.typing = typing

    def is_typing(self):
        return self.typing

    def mark_as_read(self):
        receipts = []
        for message in self.messages:
            if not (message.is_sent_by_me() or message.is_read()):
                receipts.append(message.uuid)
                message.mark_as_read()
        return receipts


class Data:
    def __init__(self, contacts, myself):
        assert myself not in contacts
        self.contacts = contacts
        self.histories = []
        self.history_by_contact = {}
        self.myself = myself
        for contact in contacts:
            history = History(contact)
            self.history_by_contact[contact] = history
            self.histories.append(history)

    def get_history(self, index):
        return self.histories[index]

    def get_history_by_contact(self, contact):
        if contact in self.history_by_contact:
            return self.history_by_contact[contact]
        return None


class ChatGui:
    def __init__(self, myself, on_send, on_type, on_read, typing_timeout_seconds=3):
        contacts = (
            ["team{}a".format(i) for i in range(1, 13)]
            + ["team{}b".format(i) for i in range(1, 13)]
            + ["x{}".format(i) for i in range(1, 7)]
        )
        if myself not in contacts:
            raise ValueError(
                "The value for parameter 'myself' is {}, but it needs to be one of the registered names {}.".format(
                    myself, contacts
                )
            )
        contacts.remove(myself)
        self.data = Data(contacts, myself)
        self.changed = False
        self.typing_timestamps = {}
        self.on_send = on_send
        self.on_type = on_type
        self.on_read = on_read
        self.typing_timeout_seconds = typing_timeout_seconds

    def receive(self, sender, message, message_uuid):
        history = self.data.get_history_by_contact(sender)
        if history:
            history.add_message(
                Message(sender, self.data.myself, message, message_uuid, False)
            )
            self.changed = True

    def send(self, receiver, message):
        message = Message.create_message(self.data.myself, receiver, message)
        history = self.data.get_history_by_contact(receiver)
        if history:
            history.add_message(message)
            # forward to callback
            self.on_send(self.data.myself, receiver, message.message, message.uuid)

    def typing(self, sender):
        history = self.data.get_history_by_contact(sender)
        if history:
            history.set_typing(sender)
            self.changed = True

    def receipt_read(self, sender, message_uuid):
        history = self.data.get_history_by_contact(sender)
        if history:
            history.set_send_status(message_uuid, SEND_RECEIPT_READ)
            self.changed = True

    def receipt_delivered(self, sender, message_uuid):
        history = self.data.get_history_by_contact(sender)
        if history:
            history.set_send_status(message_uuid, SEND_RECEIPT_DELIVERED)
            self.changed = True

    def call_list(self, sender, data):
        self.changed = True

    def call_send_button(self, sender_widget, data):
        message = get_value("##mes")
        index = get_value("##list")
        receiver = self.data.get_history(index).contact
        self.typing_timestamps[receiver] = None
        set_value("##mes", "")
        if sender_widget == "Button##SendAll":
            for receiver in self.data.contacts:
                self.send(receiver, message)
        else:
            self.send(receiver, message)
        self.changed = True

    def call_write(self, sender_widget, data):
        index = get_value("##list")
        receiver = self.data.get_history(index).contact
        now = time.time()
        if receiver in self.typing_timestamps:
            last_timestamp = self.typing_timestamps[receiver]
            if (last_timestamp is not None) and (
                now - last_timestamp < self.typing_timeout_seconds
            ):
                return
        self.typing_timestamps[receiver] = now
        # call typing callback
        self.on_type(self.data.myself, receiver)

    def main_callback(self, sender, data):
        if self.changed:
            self.changed = False
            clear_table("Table##Messages")
            index = get_value("##list")
            history = self.data.get_history(index)
            for message_uuid in history.mark_as_read():
                self.on_read(self.data.myself, history.contact, message_uuid)
            if history.is_typing():
                set_value("Label", "{} is typing...".format(history.contact))
                history.set_typing(False)
            else:
                set_value("Label", "")
            set_table_data("Table##Messages", history._get_rows())

    def show(self):

        with window(
            "MQTT Message Chat",
            width=400,
            height=500,
        ):
            add_label_text("MyID", label="", color=[0, 200, 255])
            set_value("MyID", "Me: " + self.data.myself)
            add_listbox(
                "##list",
                items=self.data.contacts,
                width=150,
                callback=self.call_list,
            )
            add_same_line()
            with group("MessagesG", horizontal=False):
                add_table("Table##Messages", ["Messages"], width=300, height=400)
                add_label_text("Label", label="", color=[0, 200, 255])
                add_input_text(
                    "##mes",
                    default_value="",
                    multiline=True,
                    label="",
                    width=300,
                    height=80,
                    hint="Write...",
                    callback=self.call_write,
                )
                add_button(
                    "Button##Send",
                    label="Send",
                    width=145,
                    callback=self.call_send_button,
                )
                add_same_line()
                add_button(
                    "Button##SendAll",
                    label="Send To All",
                    width=145,
                    callback=self.call_send_button,
                )

        set_render_callback(self.main_callback)
        set_main_window_size(470, 550)
        # set_theme("Light")
        start_dearpygui(
            primary_window="MQTT Message Chat",
        )