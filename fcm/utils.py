import json
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_text
from django.conf import settings
from django.utils.module_loading import import_module
from pyfcm import FCMNotification

DEFAULT_FCM_DEVICE_MODEL = 'fcm.Device'


def get_device_model():
    model = getattr(settings, "FCM_DEVICE_MODEL", DEFAULT_FCM_DEVICE_MODEL)
    try:
        return apps.get_model(model)
    except ValueError:
        raise ImproperlyConfigured("FCM_DEVICE_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "FCM_DEVICE_MODEL refers to model '%s' that has not been installed" % settings.FCM_DEVICE_MODEL
        )


class FCMMessage(object):

    def __init__(self):
        """
        you will not reach to test self.api_key if it is not set in settings...
        """
        try:
            self.api_key = settings.FCM_APIKEY
        except AttributeError:
            raise ImproperlyConfigured(
                "You haven't set the 'FCM_APIKEY' setting yet.")

        """
        accessing settings.FCM_MAX_RECIPIENTS if not set
        will crash the app, it can be set to 1 by default
        """
        try:
            self.max_recipients = settings.FCM_MAX_RECIPIENTS
        except AttributeError:
            # some kind of warning would be nice
            print("Using default settings.FCM_MAX_RECIPIENTS value 1. Change it via settings")
            self.max_recipients = 1

        self.push_service = FCMNotification(api_key=self.api_key)

    def _chunks(self, items, limit):
        """
            Yield successive chunks from list \a items with a minimum size \a limit
        """
        for i in range(0, len(items), limit):
            yield items[i:i + limit]

    def send(self, data, registration_ids=None, **kwargs):
        if len(registration_ids) == 1:
            response = self.push_service.notify_single_device(
                registration_id=registration_ids[0], data_message=data,
                **kwargs
            )
        else:
            response = self.push_service.notify_multiple_devices(
                registration_ids=registration_ids,
                data_message=data, **kwargs
            )
        return registration_ids, response


class FCMMessage(FCMMessage):
    FCM_INVALID_ID_ERRORS = ['InvalidRegistration',
                             'NotRegistered',
                             'MismatchSenderId']

    def send(self, data, registration_ids=None, **kwargs):
        response = super(FCMMessage, self).send(
            data, registration_ids=registration_ids, **kwargs)
        chunks = [response] if not isinstance(response, list) else response
        for chunk in chunks:
            self.post_send(*chunk)
        return response

    def post_send(self, registration_ids, response):
        if response.get('failure'):
            invalid_messages = dict(filter(
                lambda x: x[1].get('error') in self.FCM_INVALID_ID_ERRORS,
                zip(registration_ids, response.get('results'))))

            regs = list(invalid_messages.keys())
            for device in get_device_model().objects.filter(reg_id__in=regs):
                device.mark_inactive(
                    error_message=invalid_messages[device.reg_id]['error'])
