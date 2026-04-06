from django.core.management.base import BaseCommand

from compliance.models import Control, Domain, Standard
from compliance.services.keywords import build_keywords_from_text


class Command(BaseCommand):
    help = 'Seed NCA cybersecurity standard'

    def handle(self, *args, **kwargs):
        # Delete existing NCA data to avoid duplicates
        Standard.objects.filter(name='NCA').delete()

        standard = Standard.objects.create(
            name='NCA',
            description='National Cybersecurity Authority - Essential Cybersecurity Controls (ECC)'
        )

        data = {
            'Cybersecurity Governance': [
                ('Cybersecurity Strategy', 'Establish and maintain a cybersecurity strategy aligned with organizational objectives.'),
                ('Cybersecurity Policy', 'Develop, approve, and publish a cybersecurity policy.'),
                ('Cybersecurity Roles', 'Define and assign cybersecurity roles and responsibilities.'),
                ('Cybersecurity Review', 'Conduct periodic review of cybersecurity governance documents.'),
            ],
            'Cybersecurity Risk Management': [
                ('Risk Assessment', 'Identify and assess cybersecurity risks to organizational assets.'),
                ('Risk Treatment', 'Define and implement risk treatment plans for identified risks.'),
                ('Risk Acceptance', 'Document and approve accepted cybersecurity risks.'),
                ('Third Party Risk', 'Assess and manage cybersecurity risks from third parties.'),
            ],
            'Cybersecurity Compliance': [
                ('Regulatory Compliance', 'Identify and comply with applicable cybersecurity laws and regulations.'),
                ('Compliance Monitoring', 'Monitor and measure compliance with cybersecurity requirements.'),
                ('Audit Management', 'Plan and conduct periodic cybersecurity audits.'),
            ],
            'Human Cybersecurity': [
                ('Security Awareness', 'Implement a cybersecurity awareness and training program.'),
                ('Personnel Screening', 'Perform background checks on personnel with access to critical systems.'),
                ('Acceptable Use', 'Define acceptable use policies for organizational assets.'),
                ('Termination Procedures', 'Revoke access and recover assets upon personnel termination.'),
            ],
            'Information Asset Management': [
                ('Asset Inventory', 'Maintain an inventory of all information assets.'),
                ('Asset Classification', 'Classify information assets based on sensitivity and criticality.'),
                ('Asset Handling', 'Define procedures for handling assets based on their classification.'),
                ('Asset Disposal', 'Securely dispose of assets containing sensitive information.'),
            ],
            'Identity and Access Management': [
                ('Access Control Policy', 'Establish and enforce an access control policy.'),
                ('User Registration', 'Implement formal user registration and de-registration procedures.'),
                ('Privileged Access', 'Control and monitor privileged access to systems and data.'),
                ('Multi-Factor Authentication', 'Enforce multi-factor authentication for critical systems.'),
                ('Password Management', 'Implement a strong password management policy.'),
            ],
            'Information Systems Security': [
                ('Secure Configuration', 'Apply secure configurations to all information systems.'),
                ('Vulnerability Management', 'Identify, assess, and remediate system vulnerabilities.'),
                ('Patch Management', 'Apply security patches in a timely manner.'),
                ('Malware Protection', 'Deploy and maintain malware protection on all systems.'),
                ('Logging and Monitoring', 'Enable logging and monitoring of system activities.'),
            ],
            'Data and Privacy Protection': [
                ('Data Protection Policy', 'Establish a data protection and privacy policy.'),
                ('Data Encryption', 'Encrypt sensitive data at rest and in transit.'),
                ('Data Backup', 'Implement regular data backup and recovery procedures.'),
                ('Data Retention', 'Define and enforce data retention and deletion policies.'),
            ],
            'Cybersecurity Incident Management': [
                ('Incident Response Plan', 'Develop and maintain a cybersecurity incident response plan.'),
                ('Incident Detection', 'Implement mechanisms to detect cybersecurity incidents.'),
                ('Incident Reporting', 'Define procedures for reporting cybersecurity incidents.'),
                ('Incident Recovery', 'Implement procedures to recover from cybersecurity incidents.'),
                ('Lessons Learned', 'Conduct post-incident reviews and apply lessons learned.'),
            ],
            'Physical Security': [
                ('Physical Access Control', 'Restrict and monitor physical access to critical facilities.'),
                ('Secure Areas', 'Define and protect secure areas housing critical systems.'),
                ('Equipment Protection', 'Protect equipment from physical threats and environmental hazards.'),
            ],
            'Network Security': [
                ('Network Segmentation', 'Segment networks to limit the impact of security incidents.'),
                ('Firewall Management', 'Deploy and manage firewalls to control network traffic.'),
                ('Remote Access', 'Secure and monitor remote access to organizational systems.'),
                ('Wireless Security', 'Implement security controls for wireless networks.'),
            ],
            'Cybersecurity Resilience': [
                ('Business Continuity', 'Develop and maintain a cybersecurity business continuity plan.'),
                ('Disaster Recovery', 'Implement disaster recovery procedures for critical systems.'),
                ('Resilience Testing', 'Conduct periodic testing of continuity and recovery plans.'),
            ],
        }

        for domain_name, controls in data.items():
            domain = Domain.objects.create(standard=standard, name=domain_name)
            for title, description in controls:
                Control.objects.create(
                    domain=domain,
                    title=title,
                    description=description,
                    keywords=build_keywords_from_text(title, description),
                )

        self.stdout.write(self.style.SUCCESS('NCA standard seeded successfully!'))