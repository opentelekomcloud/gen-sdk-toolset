:original_name: sfs_02_0021.html

.. _sfs_02_0021:

Creating a Shared File System (Deprecated)
==========================================

This API is no longer available.

Function
--------

This API is used to create a shared file system. After the file system is created, you need to mount the file system to ECSs to achieve shared file storage.

.. note::

   This API is an asynchronous API. If the returned status code is **200**, the API request is successfully delivered and received. Later, you can query the status and path of the shared file system by referring to :ref:`Querying Details About a Shared File System <sfs_02_0024>` to identify whether the creation is complete and successful. If the status of the shared file system becomes **available** or the shared path is generated, the creation is successful.

.. important::

   After a shared file system is created successfully, it can be used only after you add share access rules by referring to :ref:`Adding a File System Access Rule <sfs_02_0029>`.

URI
---

-  POST /v2/{project_id}/shares
-  Parameter description

   ========== ========= ====== =========================================
   Parameter  Mandatory Type   Description
   ========== ========= ====== =========================================
   project_id Yes       String Specifies the project ID of the operator.
   ========== ========= ====== =========================================

Request
-------

-  Parameter description

   +-----------+-----------+--------+----------------------------------------------------------+
   | Parameter | Mandatory | Type   | Description                                              |
   +===========+===========+========+==========================================================+
   | share     | Yes       | Object | For details, see the description of the **share** field. |
   +-----------+-----------+--------+----------------------------------------------------------+

-  Description of the **share** field

   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter         | Mandatory       | Type            | Description                                                                                                                                                                                                                                                                                       |
   +===================+=================+=================+===================================================================================================================================================================================================================================================================================================+
   | share_proto       | Yes             | String          | Specifies the file sharing protocol. The value can be **NFS** (for Linux OS).                                                                                                                                                                                                                     |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | size              | Yes             | Integer         | Specifies the size (GB) of the shared file system. The applied capacity of the shared file system cannot be larger than the allowed quota. To view the allowed quota, see :ref:`Quota Management <sfs_02_0032>`.                                                                                  |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | name              | No              | String          | Specifies the name of the shared file system, which contains 0 to 255 characters and can contain only letters, digits, hyphens (-), and underscores (_).                                                                                                                                          |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | description       | No              | String          | Specifies the description of the shared file system, which contains 0 to 255 characters and can contain only letters, digits, hyphens (-), and underscores (_).                                                                                                                                   |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | is_public         | No              | Boolean         | (Supported by API versions from v2.8 to v2.42). Specifies whether a file system can be publicly seen. If it is set to **true**, the file system can be seen publicly. If it is set to **false**, the file system can be seen privately. The default value is **false**.                           |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | availability_zone | No              | String          | Specifies the availability zone name. If this parameter is left blank, the default availability zone will be used. If the default availability zone contains no storage resources, the creation of the shared file system fails. The value contains 0 to 255 characters.                          |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | metadata          | No              | Object          | Specifies the metadata information used to create the shared file system. The value consists of one or more key and value pairs organized as a dictionary of strings. For details, see the description of the **metadata** field.                                                                 |
   |                   |                 |                 |                                                                                                                                                                                                                                                                                                   |
   |                   |                 |                 | .. caution::                                                                                                                                                                                                                                                                                      |
   |                   |                 |                 |                                                                                                                                                                                                                                                                                                   |
   |                   |                 |                 |    CAUTION:                                                                                                                                                                                                                                                                                       |
   |                   |                 |                 |                                                                                                                                                                                                                                                                                                   |
   |                   |                 |                 |    -  For security concerns, the API for modifying the **metadata** field is not opened yet. Therefore, ensure that the parameters and values are correct when creating a shared file system with data encryption using the **metadata** field.                                                   |
   |                   |                 |                 |    -  Unless otherwise specified (for example, **#sfs_crypt_key_id**), the keys that comply with the following rules in the **metadata** field are for internal use of the system. Do not customize the settings to avoid internal system errors caused by conflicts with system predefined keys. |
   |                   |                 |                 |                                                                                                                                                                                                                                                                                                   |
   |                   |                 |                 |       -  Key **share_used**                                                                                                                                                                                                                                                                       |
   |                   |                 |                 |       -  Keys that start with **#sfs**                                                                                                                                                                                                                                                            |
   +-------------------+-----------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

-  Description of **metadata** fields (creating a shared file system with the encryption function)

   When creating a shared file system with the encryption function, obtain the key ID, domain ID, and key alias of the encryption key using the HTTPS request by referring to section **Querying the List of CMKs** in the *Key Management Service API Reference*. Then, in the **metadata** field, set the key-value pairs according to the following table. Ensure that the key-value pairs in the **metadata** field are correct.

   To create a shared file system with the encryption function, all parameters in the following table are mandatory. If the encryption function is not needed, these parameters are optional.

   +----------------------+-----------------+-----------------+-------------------------------------------------------------------------------------------------------------------------------------+
   | Key                  | Value Type      | Mandatory       | Description                                                                                                                         |
   +======================+=================+=================+=====================================================================================================================================+
   | #sfs_crypt_key_id    | String          | Yes             | Specifies the encryption key ID.                                                                                                    |
   |                      |                 |                 |                                                                                                                                     |
   |                      |                 |                 | If this field, **#sfs_crypt_domain_id**, and **#sfs_crypt_alias** exist at the same time, the data encryption function is enabled.  |
   +----------------------+-----------------+-----------------+-------------------------------------------------------------------------------------------------------------------------------------+
   | #sfs_crypt_domain_id | String          | Yes             | Specifies the tenant domain ID.                                                                                                     |
   |                      |                 |                 |                                                                                                                                     |
   |                      |                 |                 | If this field, **#sfs_crypt_key_id**, and **#sfs_crypt_alias** exist at the same time, the data encryption function is enabled.     |
   +----------------------+-----------------+-----------------+-------------------------------------------------------------------------------------------------------------------------------------+
   | #sfs_crypt_alias     | String          | Yes             | Specifies the encryption key alias.                                                                                                 |
   |                      |                 |                 |                                                                                                                                     |
   |                      |                 |                 | If this field, **#sfs_crypt_key_id**, and **#sfs_crypt_domain_id** exist at the same time, the data encryption function is enabled. |
   +----------------------+-----------------+-----------------+-------------------------------------------------------------------------------------------------------------------------------------+

   .. note::

      -  You are advised to use the default key **sfs/default** to create an encrypted shared file system. For details, see section "File System Encryption" and "Encryption" in the *Scalable File Service User Guide*.

-  Example request: POST https://{endpoint}/v2/16e1ab15c35a457e9c2b2aa189f544e1/shares

   Creating a 1-GB NFS file system that can only be seen privately

   .. code-block::

      {
         "share": {
             "name": "test",
             "description": "test description",
             "share_proto": "NFS",
             "share_network_id": null,
             "size": 1,
             "is_public": false
         }
      }

-  Example request (creating a shared file system with data encryption function): POST https://{endpoint}/v2/16e1ab15c35a457e9c2b2aa189f544e1/shares

   Creating a 1-GB, encrypted NFS file system that can only be seen privately

   .. code-block::

      {
         "share": {
             "name": "test",
             "description": "test description",
             "metadata": {
                 "#sfs_crypt_key_id": "9130c90d-73b8-4203-b790-d49f98d503df",
                 "#sfs_crypt_domain_id": "3b2d9670690444c582942801ed7d457b",
                 "#sfs_crypt_alias": "sfs/default"
             },
             "share_proto": "NFS",
             "share_network_id": null,
             "size": 1,
             "is_public": false
         }
      }

Response
--------

-  Parameter description

   +-----------+--------+----------------------------------------------------------+
   | Parameter | Type   | Description                                              |
   +===========+========+==========================================================+
   | share     | Object | For details, see the description of the **share** field. |
   +-----------+--------+----------------------------------------------------------+

-  Description of the **share** field

   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter           | Type    | Description                                                                                                                                                                                                                                |
   +=====================+=========+============================================================================================================================================================================================================================================+
   | links               | Array   | Specifies the links of shared file systems.                                                                                                                                                                                                |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | availability_zone   | String  | Specifies the availability zone.                                                                                                                                                                                                           |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | share_server_id     | String  | Specifies the ID for managing share services.                                                                                                                                                                                              |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | id                  | String  | Specifies the ID of the shared file system.                                                                                                                                                                                                |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | size                | Integer | Specifies the size (GB) of the shared file system.                                                                                                                                                                                         |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | project_id          | String  | Specifies the ID of the project to which the shared file system belongs.                                                                                                                                                                   |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | metadata            | Object  | Sets one or more metadata key and value pairs as a dictionary of strings. The value of the **share_used** key indicates the file system used capacity, in bytes.                                                                           |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | status              | String  | Specifies the status of the shared file system.                                                                                                                                                                                            |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | description         | String  | Describes the shared file system.                                                                                                                                                                                                          |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | host                | String  | Specifies the name of the host. This field is visible only to the administrator.                                                                                                                                                           |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | name                | String  | Specifies the name of the shared file system.                                                                                                                                                                                              |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | created_at          | String  | Specifies the date and time stamp when the shared file system was created.                                                                                                                                                                 |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | access_rules_status | String  | Specifies the configuration status of the access rule. Possible values are **active** (effective), **error** (configuration failed), and **syncing** (configuration in progress). This field is supported by API v2.10 and later versions. |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | share_proto         | String  | Specifies the protocol for sharing file systems.                                                                                                                                                                                           |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | share_type_name     | String  | Specifies the storage service type assigned for the shared file system, such as high-performance storage (composed of SSDs) and large-capacity storage (composed of SATA disks). This field is supported by API v2.6 and later versions.   |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | share_type          | String  | Specifies the ID of the file system type.                                                                                                                                                                                                  |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | volume_type         | String  | Specifies the volume type. The definition of this parameter is the same as that of **share_type**.                                                                                                                                         |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | export_locations    | Array   | Lists the mount locations. Currently, only a single mount location is supported. This parameter exists only when **X-Openstack-Manila-Api-Version** specified in the request header is smaller than **2.9**.                               |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | export_location     | String  | Specifies the mount location. This parameter exists only when **X-Openstack-Manila-Api-Version** specified in the request header is smaller than **2.9**.                                                                                  |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | is_public           | Boolean | Specifies the visibility level of the shared file system. If **true** is returned, the file system can be seen publicly. If **false** is returned, the file system can be seen privately. The default value is **false**.                  |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | user_id             | String  | Specifies the user ID. This field is supported by API v2.16 and later versions.                                                                                                                                                            |
   +---------------------+---------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

-  Example response

   .. code-block::

      {
          "share": {
              "status": "creating",
              "project_id": "16e1ab15c35a457e9c2b2aa189f544e1",
              "name": "share_London",
              "share_type": "25747776-08e5-494f-ab40-a64b9d20d8f7",
              "availability_zone": "az1.dc1",
              "created_at": "2015-09-18T10:25:24.533287",
              "export_location": null,
              "links": [
                  {
                      "href": "http://192.168.198.54:8786/v2/16e1ab15c35a457e9c2b2aa189f544e1/shares/011d21e2-fbc3-4e4a-9993-9ea223f73264",
                      "rel": "self"
                  },
                  {
                      "href": "http://192.168.198.54:8786/16e1ab15c35a457e9c2b2aa189f544e1/shares/011d21e2-fbc3-4e4a-9993-9ea223f73264",
                      "rel": "bookmark"
                  }
              ],
              "share_network_id": null,
              "export_locations": [],
              "share_proto": "NFS",
              "host": null,
              "volume_type": "default",
              "snapshot_id": null,
              "is_public": true,
              "metadata": {
                  "project": "my_app",
                  "aim": "doc"
              },
              "id": "011d21e2-fbc3-4e4a-9993-9ea223f73264",
              "size": 1,
              "description": "My custom share London"
          }
      }

   .. note::

      When the client receives the system response, the shared file system is still being created. For this reason, the shared path cannot be queried immediately. You can use the API of :ref:`Querying Mount Locations of a Shared File System <sfs_02_0025>` to query the shared path after the creation is complete.

Status Codes
------------

-  Normal

   200

-  Abnormal

   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | Status Code                       | Description                                                                                |
   +===================================+============================================================================================+
   | 400 Bad Request                   | The server failed to process the request.                                                  |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 401 Unauthorized                  | You must enter a username and the password to access the requested page.                   |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 403 Forbidden                     | Access to the requested page is forbidden.                                                 |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 404 Not Found                     | The requested page was not found.                                                          |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 405 Method Not Allowed            | You are not allowed to use the method specified in the request.                            |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 406 Not Acceptable                | The response generated by the server could not be accepted by the client.                  |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 407 Proxy Authentication Required | You must use the proxy server for authentication. Then the request can be processed.       |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 408 Request Timeout               | The request timed out.                                                                     |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 409 Conflict                      | The request could not be processed due to a conflict.                                      |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 413 Quota Exceeded                | Insufficient user quota.                                                                   |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 500 Internal Server Error         | Failed to complete the request because of an internal service error.                       |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 501 Not Implemented               | Failed to complete the request because the server does not support the requested function. |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 502 Bad Gateway                   | Failed to complete the request because the request is invalid.                             |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 503 Service Unavailable           | Failed to complete the request because the service is unavailable.                         |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
   | 504 Gateway Timeout               | A gateway timeout error occurred.                                                          |
   +-----------------------------------+--------------------------------------------------------------------------------------------+
