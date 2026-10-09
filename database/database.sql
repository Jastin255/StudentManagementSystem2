CREATE DATABASE IF NOT EXITS student_management3;
USE student_management3;
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('Admin', 'Teacher', 'Student') NOT NULL,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    darasa VARCHAR(50) NOT NULL,
    alama VARCHAR(10) DEFAULT 'Bado',
    ada_inayotakiwa DECIMAL(10,2) DEFAULT 500000.00,
    ada_iliyolipwa DECIMAL(10,2) DEFAULT 0.00,
    uhakiki_wa_ada VARCHAR(50) DEFAULT 'Bado Hajalipa',
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS teachers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    somo VARCHAR(100) DEFAULT 'Bado Kupangiwa',
    darasa_la_kufundisha VARCHAR(50) DEFAULT 'Bado Kupangiwa',
    mshahara DECIMAL(10,2) DEFAULT 0.00,
    hali_ya_mshahara VARCHAR(50) DEFAULT 'Haijalipwa',
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    tarehe DATE NOT NULL,
    hali VARCHAR(20) NOT NULL,
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

-- Weka watumiaji wa mfano (Default Users) ili uweze kulogin
-- Password zote hapa kwa sasa ni rahisi: admin123, teacher123, student123
INSERT IGNORE INTO users (username, password, role, name) VALUES 
('admin', 'admin123', 'Admin', 'Mkuu wa Shule'),
('mwalimu1', 'teacher123', 'Teacher', 'Mwl. Christopher'),
('mwanafunzi1', 'student123', 'Student', 'Juma Amos');

INSERT IGNORE INTO students (username, darasa, ada_inayotakiwa, ada_iliyolipwa, uhakiki_wa_ada) 
VALUES ('mwanafunzi1', 'Form 4', 500000.00, 0.00, 'Bado Hajalipa');

INSERT IGNORE INTO teachers (username, somo, darasa_la_kufundisha, mshahara) 
VALUES ('mwalimu1', 'Python Programming', 'Form 4', 800000.00);