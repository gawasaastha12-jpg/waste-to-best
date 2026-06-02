# backend/users/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import RoleChoices, Profile, UserConsentLog, VerificationDocument

User = get_user_model()

class UserAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('user_register')
        self.login_url = reverse('token_obtain_pair')
        self.profile_url = reverse('profile_detail')
        
        self.citizen_data = {
            "email": "citizen@test.com",
            "password": "securepassword123",
            "role": "citizen",
            "consent": True,
            "profile": {
                "display_name": "Test Citizen",
                "phone_number": "1234567890",
                "address_line": "123 Green St",
                "latitude": "12.9716",
                "longitude": "77.5946"
            }
        }

    def test_citizen_registration_success(self):
        response = self.client.post(self.register_url, self.citizen_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', response.data)
        
        # Verify db models exist
        user = User.objects.filter(email="citizen@test.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, RoleChoices.CITIZEN)
        
        profile = Profile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.display_name, "Test Citizen")
        
        consent = UserConsentLog.objects.filter(user=user).first()
        self.assertIsNotNone(consent)
        self.assertEqual(consent.consent_type, "privacy_policy_v1.0")

    def test_registration_fails_without_consent(self):
        invalid_data = self.citizen_data.copy()
        invalid_data['consent'] = False
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_retrieval_and_update(self):
        # 1. Register a user
        reg_response = self.client.post(self.register_url, self.citizen_data, format='json')
        access_token = reg_response.data['tokens']['access']
        
        # 2. Authenticate
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        # 3. Retrieve Profile
        get_response = self.client.get(self.profile_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['display_name'], "Test Citizen")
        
        # 4. Patch Profile
        patch_data = {"display_name": "Updated Citizen Name"}
        patch_response = self.client.patch(self.profile_url, patch_data, format='json')
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data['display_name'], "Updated Citizen Name")


class DocumentVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create users
        self.admin = User.objects.create_superuser(email="admin@test.com", password="adminpassword")
        self.ngo_user = User.objects.create_user(email="ngo@test.com", password="ngopassword", role=RoleChoices.NGO)
        Profile.objects.create(user=self.ngo_user, display_name="Test NGO")
        
        self.doc_submit_url = reverse('verification_documents')

    def test_document_submission_and_resolution(self):
        # NGO Logins
        self.client.force_authenticate(user=self.ngo_user)
        
        # Submit document
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Simple PDF format signature check requires a mock header starting with %PDF
        dummy_file = SimpleUploadedFile("license.pdf", b"%PDF-1.4 ... dummy content ...", content_type="application/pdf")
        
        submit_data = {
            "doc_type": "business_license",
            "document_file": dummy_file
        }
        submit_response = self.client.post(self.doc_submit_url, submit_data, format='multipart')
        self.assertEqual(submit_response.status_code, status.HTTP_201_CREATED)
        doc_id = submit_response.data['id']
        
        # Verify status defaults to pending
        doc = VerificationDocument.objects.get(id=doc_id)
        self.assertEqual(doc.status, VerificationDocument.StatusChoices.PENDING)
        
        # Admin Logins to approve
        self.client.force_authenticate(user=self.admin)
        resolve_url = reverse('admin_resolve_verification', kwargs={'doc_id': doc_id})
        
        resolve_data = {"status": "approved"}
        resolve_response = self.client.post(resolve_url, resolve_data, format='json')
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        
        # Verify doc status and user profile verified flag
        doc.refresh_from_db()
        self.assertEqual(doc.status, VerificationDocument.StatusChoices.APPROVED)
        
        ngo_profile = Profile.objects.get(user=self.ngo_user)
        self.assertTrue(ngo_profile.is_verified)
