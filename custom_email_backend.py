import ssl
from django.core.mail.backends.smtp import EmailBackend as DjangoSmtpEmailBackend
from django.conf import settings

class CustomSmtpEmailBackend(DjangoSmtpEmailBackend):
    def open(self):
        """
        Ensures we don't use the default SSL settings if not applicable,
        and calls starttls() without keyfile/certfile if use_tls is True.
        """
        if self.connection:
            return False  # Connection already open

        # If DANE is used, SSL context is already handled by DANEBackend.
        # If local settings have CERTFILE and KEYFILE, those are used.
        # Else, a customized context is created with default certs.
        if self.ssl_certfile or self.ssl_keyfile or settings.DATABASES.get('default', {}).get('CONN_MAX_AGE'): #CONN_MAX_AGE is just a placeholder to trigger the original logic if certs were set
             # This part is from the original Django 4.1.13 backend.
             # We keep it in case those settings *are* legitimately used for SSL, not TLS.
            self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            if self.ssl_certfile:
                self.ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
            # Set minimum TLS version to 1.2 by default (can be overridden by settings).
            self.ssl_context.minimum_version = getattr(
                settings, "EMAIL_SSL_MIN_TLS_VERSION", ssl.TLSVersion.TLSv1_2
            )
            # Explicitly enable check_hostname if not already.
            if self.ssl_context.check_hostname is False:
                self.ssl_context.check_hostname = True


        connection_kwargs = {}
        if self.timeout is not None:
            connection_kwargs["timeout"] = self.timeout
        if self.use_ssl:
            connection_kwargs["context"] = self.ssl_context
            self.connection = self.connection_class(
                self.host, self.port, **connection_kwargs
            )
        else:
            self.connection = self.connection_class(
                self.host, self.port, **connection_kwargs
            )

        if self.use_tls:
            # This is the CRITICAL part we are overriding for use_tls=True
            # We ensure keyfile and certfile are NOT passed to starttls()
            # The context argument is important for modern Python versions.
            # Create a default context if one wasn't created above (e.g. if not use_ssl)
            tls_context = getattr(self, 'ssl_context', None)
            if tls_context is None:
                tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                # Set minimum TLS version to 1.2 by default (can be overridden by settings).
                tls_context.minimum_version = getattr(
                    settings, "EMAIL_SSL_MIN_TLS_VERSION", ssl.TLSVersion.TLSv1_2
                )
                # Explicitly enable check_hostname if not already.
                if tls_context.check_hostname is False:
                    tls_context.check_hostname = True

            try:
                self.connection.starttls(context=tls_context) # CALL WITHOUT keyfile/certfile
                self.connection.ehlo()
            except Exception as e:
                self.close()
                raise e


        if self.username and self.password:
            try:
                self.connection.login(self.username, self.password)
            except Exception as e:
                self.close()
                raise e
        return True