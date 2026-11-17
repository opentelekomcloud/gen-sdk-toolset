:original_name: iam_02_0510.html

.. _iam_02_0510:

Authentication
==============

Requests for calling an API can be authenticated using either of the following methods:

-  Token-based authentication: Requests are authenticated using a token.
-  AK/SK-based authentication: Requests are authenticated by encrypting the request body using an AK/SK pair.

Token-based Authentication
--------------------------

.. note::

   The validity period of a token is 24 hours. When using a token for authentication, cache it to prevent frequently calling the IAM API used to obtain a user token.

A token specifies temporary permissions in a computer system. During API authentication using a token, the token is added to request headers to get permissions for calling the API.

You can obtain a token by calling the API described in :ref:`Obtaining a User Token Through Password Authentication <en-us_topic_0057845583>`. IAM APIs can be called only by using a global service token. To call the API described in :ref:`Obtaining a User Token Through Password Authentication <en-us_topic_0057845583>`, set **auth.scope** to **domain** in the request body. In the following example, **DomainName** indicates the account name:

.. code-block::

   {
       "auth": {
           "identity": {
               "methods": [
                   "password"
               ],
               "password": {
                   "user": {
                       "domain": {
                           "name": "DomainName"
                       },
                       "name": "IAMUserName",
                       "password": "IAMUserPassWord"
                   }
               }
           },
           "scope": {
               "domain": {
                   "name": "DomainName"
               }
           }
       }
   }

After a token is obtained, the **X-Auth-Token** header field must be added to requests to specify the token when calling other APIs. For example, if the token is **ABCDEFJ....**, **X-Auth-Token: ABCDEFJ....** can be added to a request as follows:

.. code-block::


   GET https://iam.region1.example.com/v3/auth/projects
   Content-Type: application/json
   X-Auth-Token: ABCDEFJ....

AK/SK-based Authentication
--------------------------

.. note::

   AK/SK-based authentication supports API requests with a body not larger than 12 MB. For API requests with a larger body, token-based authentication is recommended.

In AK/SK-based authentication, AK/SK is used to sign requests and the signature is then added to the requests for authentication.

-  AK: access key ID, which is a unique identifier used in conjunction with a secret access key to sign requests cryptographically.
-  SK: secret access key used in conjunction with an AK to sign requests cryptographically. It identifies a request sender and prevents the request from being modified.

In AK/SK-based authentication, you can use an AK/SK pair to sign requests based on the signature algorithm or use the signing SDK to sign requests.

.. important::

   The signing SDK is only used for signing requests and is different from the SDKs provided by services.
