src/controllers/resumeController.js 

const { uploadResume, getResume } = require('../services/resumeService');
const { BlobServiceClient } = require('@azure/storage-blob');

const containerName = process.env.RESUME_CONTAINER_NAME;
const blobServiceClient = BlobServiceClient.fromConnectionString(process.env.AZURE_STORAGE_CONNECTION_STRING);

async function upload(req, res) {
    try {
        if (!req.file) return res.status(400).json({ message: 'File is required' });
        const resume = await uploadResume(req.file, req.user.id);
        res.status(201).json({ message: 'Resume uploaded', resume });
    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Internal server error' });
    }
}

async function download(req, res) {
    try {
        const resume = await getResume(req.user.id, req.params.id);
        const containerClient = blobServiceClient.getContainerClient(containerName);
        const blockBlobClient = containerClient.getBlockBlobClient(resume.storagePath);
        const downloadBlockBlobResponse = await blockBlobClient.download();
        res.setHeader('Content-Disposition', `attachment; filename="${resume.fileName}"`);
        downloadBlockBlobResponse.readableStreamBody.pipe(res);
    } catch (err) {
        console.error(err);
        res.status(404).json({ message: 'Resume not found' });
    }
}

module.exports = { upload, download };


src/services/resumeService.js 

const { BlobServiceClient } = require('@azure/storage-blob');
const Resume = require('../models/resumeModel');

const blobServiceClient = BlobServiceClient.fromConnectionString(process.env.AZURE_STORAGE_CONNECTION_STRING);
const containerName = process.env.RESUME_CONTAINER_NAME;

async function uploadResume(file, userId) {
    const containerClient = blobServiceClient.getContainerClient(containerName);
    const blobName = `${userId}/${Date.now()}_${file.originalname}`;
    const blockBlobClient = containerClient.getBlockBlobClient(blobName);
    await blockBlobClient.uploadData(file.buffer, {
        blobHTTPHeaders: { blobContentType: file.mimetype }
    });
    const resume = new Resume({
        userId,
        fileName: file.originalname,
        fileType: file.mimetype,
        fileSize: file.size,
        storagePath: blobName
    });
    await resume.save();
    return resume;
}

async function getResume(userId, resumeId) {
    const resume = await Resume.findOne({ _id: resumeId, userId });
    if (!resume) throw new Error('Resume not found');
    return resume;
}

module.exports = { uploadResume, getResume };


src/models/resumeModel.js 

const mongoose = require('mongoose');

const resumeSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    fileName: { type: String, required: true },
    fileType: { type: String, required: true },
    fileSize: { type: Number, required: true },
    storagePath: { type: String, required: true },
    uploadedAt: { type: Date, default: Date.now },
}, { timestamps: true });

module.exports = mongoose.model('Resume', resumeSchema);


src/middlewares/validateFile.js 

module.exports = function validateFile(req, res, next) {
    const file = req.file;
    if (!file) return res.status(400).json({ message: 'File is required' });

    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!allowedTypes.includes(file.mimetype)) return res.status(400).json({ message: 'Invalid file type' });

    if (file.size > parseInt(process.env.MAX_FILE_SIZE)) return res.status(400).json({ message: 'File too large' });
    next();
};


src/middlewares/rateLimiter.js 

const rateLimit = require('express-rate-limit');

module.exports = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 100,
    message: 'Too many requests from this IP, try again later'
});


src/routes/resumeRoutes.js 

const express = require('express');
const multer = require('multer');
const { upload, download } = require('../controllers/resumeController');
const authMiddleware = require('../middlewares/authMiddleware');
const validateFile = require('../middlewares/validateFile');
const rateLimiter = require('../middlewares/rateLimiter');

const router = express.Router();
const uploadMiddleware = multer({ storage: multer.memoryStorage() });

router.post('/resumes', authMiddleware, rateLimiter, uploadMiddleware.single('file'), validateFile, upload);
router.get('/resumes/:id/download', authMiddleware, rateLimiter, download);

module.exports = router;
