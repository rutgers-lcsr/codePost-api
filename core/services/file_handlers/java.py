# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import re
import logging
from typing import Set, Optional

from .base import BaseFileHandler

logger = logging.getLogger(__name__)

class JavaHandler(BaseFileHandler):
    
    # Common library mapping
    MAPPING = {
        'org.junit': 'junit:junit:4.13.2',
        'org.junit.jupiter': 'org.junit.jupiter:junit-jupiter:5.9.2',
        'org.testng': 'org.testng:testng:7.7.0',
        'com.google.gson': 'com.google.code.gson:gson:2.10.1',
        'com.fasterxml.jackson': 'com.fasterxml.jackson.core:jackson-databind:2.15.2',
        'org.apache.commons.lang3': 'org.apache.commons:commons-lang3:3.12.0',
        'org.apache.commons.io': 'commons-io:commons-io:2.13.0',
        'com.google.common': 'com.google.guava:guava:32.1.1-jre',
        'org.mockito': 'org.mockito:mockito-core:5.4.0',
        'org.assertj': 'org.assertj:assertj-core:3.24.2',
        'org.slf4j': 'org.slf4j:slf4j-api:2.0.7',
        'org.json': 'org.json:json:20230618'
    }

    def get_language(self) -> str:
        return 'java-17'

    def is_executable(self) -> bool:
        return True

    def get_requirements(self) -> Optional[str]:
        # Check for pom.xml first
        if self.file.name == 'pom.xml':
            return self.content
            
        imports = self.scan_content(self.content)
        if not imports:
            return None
            
        dependencies = self._generate_pom_dependencies(imports)
        if dependencies:
            return self._generate_pom(dependencies)
        return None

    @classmethod
    def scan_content(cls, code: str) -> Set[str]:
        packages = set()
        try:
             import javalang
             tree = javalang.parse.parse(code)  # type: ignore[attr-defined]  # javalang untyped
             for _path, node in tree.filter(javalang.tree.Import):  # type: ignore[attr-defined]  # javalang untyped
                 if node.path:  # type: ignore[attr-defined]  # javalang untyped
                     packages.add(node.path)  # type: ignore[attr-defined]  # javalang untyped
        except ImportError:
            # Fallback regex if javalang not installed
            matches = re.findall(r'import\s+([\w\.]+);', code)
            packages.update(matches)
        except Exception:
            pass # Parsing error
        return packages

    def _generate_pom_dependencies(self, imports: Set[str]) -> Set[str]:
        artifacts = set()
        for imp in imports:
            for prefix, coord in self.MAPPING.items():
                if imp.startswith(prefix):
                    artifacts.add(coord)
                    break
        return artifacts

    def _generate_pom(self, artifacts: Set[str]) -> str:
        deps = []
        for arti in sorted(artifacts):
            parts = arti.split(':')
            if len(parts) >= 3:
                deps.append(f"""
        <dependency>
            <groupId>{parts[0]}</groupId>
            <artifactId>{parts[1]}</artifactId>
            <version>{parts[2]}</version>
        </dependency>""")
        
        deps_str = "\n".join(deps)
        
        return f"""<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
 
  <groupId>com.codepost.assignment</groupId>
  <artifactId>submission</artifactId>
  <version>1.0-SNAPSHOT</version>
 
  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
  </properties>
 
  <dependencies>{deps_str}
  </dependencies>
</project>"""
