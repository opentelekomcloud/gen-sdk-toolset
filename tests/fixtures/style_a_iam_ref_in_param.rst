:original_name: iam_02_0021.html

.. _iam_02_0021:

Modifying the Operation Protection Policy
=========================================

Function
--------

This API is provided for the administrator to modify the operation protection policy.

URI
---

PUT /v3.0/OS-SECURITYPOLICY/domains/{domain_id}/protect-policy

.. table:: **Table 1** URI parameters

   ========= ========= ====== ===========
   Parameter Mandatory Type   Description
   ========= ========= ====== ===========
   domain_id Yes       String Domain ID.
   ========= ========= ====== ===========

Request Parameters
------------------

.. table:: **Table 2** Parameters in the request header

   +--------------+-----------+--------+----------------------------------------------------+
   | Parameter    | Mandatory | Type   | Description                                        |
   +==============+===========+========+====================================================+
   | X-Auth-Token | Yes       | String | Token with **Security Administrator** permissions. |
   +--------------+-----------+--------+----------------------------------------------------+

.. table:: **Table 3** Parameters in the request body

   +-------------------------------------------------------+-----------+--------+------------------------------+
   | Parameter                                             | Mandatory | Type   | Description                  |
   +=======================================================+===========+========+==============================+
   | :ref:`protect_policy <iam_02_0021__table54451161197>` | Yes       | object | Operation protection policy. |
   +-------------------------------------------------------+-----------+--------+------------------------------+

.. _iam_02_0021__table54451161197:

.. table:: **Table 4** protect_policy

   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter                                          | Mandatory | Type                 | Description                                                                                                                                                                                                                                                |
   +====================================================+===========+======================+============================================================================================================================================================================================================================================================+
   | operation_protection                               | Yes       | Boolean              | Whether to enable operation protection. The value can be **true** (enable) or **false** (disable).                                                                                                                                                         |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | :ref:`allow_user <iam_02_0021__table744064115287>` | No        | AllowUserBody object | Attributes that IAM users can modify.                                                                                                                                                                                                                      |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | mobile                                             | No        | String               | Mobile number specified for operation protection verification. This parameter is mandatory when **admin_check** is set to **on** and **scene** is set to **mobile**. Example: 0001-123456789                                                               |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | admin_check                                        | No        | String               | Whether to designate a person for verification. If this parameter is set to **on**, you need to specify the **scene** parameter to designate a person for verification. If this parameter is set to **off**, the operator is responsible for verification. |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | email                                              | No        | String               | Email address specified for operation protection verification. This parameter is mandatory when **admin_check** is set to **on** and **scene** is set to **email**. Example: example@email.com                                                             |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | scene                                              | No        | String               | Verification method set for the specified person. This parameter is mandatory when **admin_check** is set to **on**. The value options are **mobile** and **email**.                                                                                       |
   +----------------------------------------------------+-----------+----------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

.. _iam_02_0021__table744064115287:

.. table:: **Table 5** protect_policy.allow_user

   +------------------+-----------+---------+--------------------------------------------------------------------------------------------------------+
   | Parameter        | Mandatory | Type    | Description                                                                                            |
   +==================+===========+=========+========================================================================================================+
   | manage_accesskey | No        | Boolean | Whether IAM users are allowed to manage AKs by themselves. The value can be **true** or **false**.     |
   +------------------+-----------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_email     | No        | Boolean | Whether IAM users are allowed to change their email addresses. The value can be **true** or **false**. |
   +------------------+-----------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_mobile    | No        | Boolean | Whether IAM users are allowed to change their mobile numbers. The value can be **true** or **false**.  |
   +------------------+-----------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_password  | No        | Boolean | Whether IAM users are allowed to change their passwords. The value can be **true** or **false**.       |
   +------------------+-----------+---------+--------------------------------------------------------------------------------------------------------+

Response Parameters
-------------------

.. table:: **Table 6** Parameters in the response body

   +-------------------------------------------------------------------+--------+------------------------------+
   | Parameter                                                         | Type   | Description                  |
   +===================================================================+========+==============================+
   | :ref:`protect_policy <iam_02_0021__response_protectpolicyresult>` | object | Operation protection policy. |
   +-------------------------------------------------------------------+--------+------------------------------+

.. _iam_02_0021__response_protectpolicyresult:

.. table:: **Table 7** protect_policy

   +----------------------------------------------------+----------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter                                          | Type                 | Description                                                                                                                                                                                                          |
   +====================================================+======================+======================================================================================================================================================================================================================+
   | :ref:`allow_user <iam_02_0021__table185786581076>` | AllowUserBody object | Attributes that IAM users can modify.                                                                                                                                                                                |
   +----------------------------------------------------+----------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | operation_protection                               | boolean              | Whether to enable operation protection. The value can be **true** or **false**.                                                                                                                                      |
   +----------------------------------------------------+----------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | admin_check                                        | String               | Whether a person is designated for verification. The value **on** indicates that a specific person is designated for verification, and the value **off** indicates that the operator is designated for verification. |
   +----------------------------------------------------+----------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | scene                                              | String               | Verification method set for the specified person.                                                                                                                                                                    |
   +----------------------------------------------------+----------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

.. _iam_02_0021__table185786581076:

.. table:: **Table 8** protect_policy.allow_user

   +------------------+---------+--------------------------------------------------------------------------------------------------------+
   | Parameter        | Type    | Description                                                                                            |
   +==================+=========+========================================================================================================+
   | manage_accesskey | boolean | Whether IAM users are allowed to manage AKs by themselves. The value can be **true** or **false**.     |
   +------------------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_email     | boolean | Whether IAM users are allowed to change their email addresses. The value can be **true** or **false**. |
   +------------------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_mobile    | boolean | Whether IAM users are allowed to change their mobile numbers. The value can be **true** or **false**.  |
   +------------------+---------+--------------------------------------------------------------------------------------------------------+
   | manage_password  | boolean | Whether IAM users are allowed to change their passwords. The value can be **true** or **false**.       |
   +------------------+---------+--------------------------------------------------------------------------------------------------------+

Example Request
---------------

.. code-block:: text

   PUT https://sample.domain.com/v3.0/OS-SECURITYPOLICY/domains/{domain_id}/protect-policy

   {
     "protect_policy" : {
       "operation_protection" : true
     }
   }

Example Response
----------------

**Status code: 200**

The request is successful.

.. code-block::

   {
    "protect_policy": {
     "allow_user": {
      "manage_mobile": true,
      "manage_accesskey": true,
      "manage_email": true,
      "manage_password": true
     },
     "operation_protection": true,
     "admin_check": "off",
     "scene": ""
    }
   }

**Status code: 400**

The request body is abnormal.

-  Example 1

.. code-block::

   {
      "error_msg" : "'%(key)s' is a required property.",
      "error_code" : "IAM.0072"
    }

-  Example 2

.. code-block::

   {
      "error_msg" : "Invalid input for field '%(key)s'. The value is '%(value)s'.",
      "error_code" : "IAM.0073"
    }

**Status code: 403**

Access denied.

-  Example 1

.. code-block::

   {
      "error_msg" : "Policy doesn't allow %(actions)s to be performed.",
      "error_code" : "IAM.0003"
    }

-  Example 2

.. code-block::

   {
      "error_msg" : "You are not authorized to perform the requested action.",
      "error_code" : "IAM.0002"
    }

**Status code: 500**

The system is abnormal.

.. code-block::

   {
     "error_msg" : "An unexpected error prevented the server from fulfilling your request.",
     "error_code" : "IAM.0006"
   }

Status Codes
------------

=========== =============================
Status Code Description
=========== =============================
200         The request is successful.
400         The request body is abnormal.
401         Authentication failed.
403         Access denied.
500         The system is abnormal.
=========== =============================
